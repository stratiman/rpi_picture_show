#!/usr/bin/env python3
"""
RPI Picture Show - Web Upload & Admin Interface.
Flask web app for uploading images and managing the slideshow.
"""

import base64
import configparser
import datetime
import functools
import hashlib
import logging
import os
import random
import shutil
import sys
import time

from flask import (
    Flask, request, redirect, url_for, Response, session, send_from_directory,
)
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("web_upload")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
ALLOWED_FOLDERS = ("logo", "pictures", "trash")

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def load_config(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


def save_config(cfg: configparser.ConfigParser, path: str):
    with open(path, "w") as f:
        cfg.write(f)


def get_config_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_free_space_mb(path: str) -> int:
    """Return free disk space in MB for the filesystem containing *path*."""
    usage = shutil.disk_usage(path)
    return int(usage.free / (1024 * 1024))


def make_timestamped_name(filename: str) -> str:
    """Return filename with timestamp inserted, e.g. 'photo_20260226_143022.jpg'."""
    name, ext = os.path.splitext(filename)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{name}_{ts}{ext}"


# ---------------------------------------------------------------------------
# Upload page HTML
# ---------------------------------------------------------------------------

HTML_UPLOAD = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#1a1a2e; color:#eee; min-height:100vh;
  display:flex; flex-direction:column; align-items:center; padding:20px; }}
.container {{ max-width:600px; width:100%; text-align:center; }}
.logo {{ margin:20px auto; max-width:280px; max-height:200px; }}
.logo img {{ max-width:100%; max-height:200px; object-fit:contain; border-radius:8px; }}
h1 {{ font-size:1.8em; margin-bottom:10px; color:#e94560; }}
.greeting {{ font-size:1.1em; color:#aaa; margin-bottom:30px; line-height:1.5; }}
.upload-area {{ background:#16213e; border:2px dashed #e94560; border-radius:12px;
  padding:40px 20px; margin-bottom:20px; transition:background 0.2s; }}
.upload-area:hover {{ background:#1a1a3e; }}
.upload-area.dragover {{ background:#1f2b4d; border-color:#ff6b81; }}
input[type="file"] {{ display:none; }}
.btn {{ display:inline-block; background:#e94560; color:#fff; border:none;
  padding:14px 32px; font-size:1.1em; border-radius:8px; cursor:pointer;
  transition:background 0.2s; text-decoration:none; }}
.btn:hover {{ background:#c73a52; }}
.btn:disabled {{ background:#555; cursor:not-allowed; }}
.btn-select {{ background:#0f3460; margin-bottom:15px; }}
.btn-select:hover {{ background:#1a4a7a; }}
.file-name {{ margin:10px 0; font-size:0.95em; color:#aaa; min-height:1.4em; }}
.message {{ padding:12px 20px; border-radius:8px; margin-bottom:20px; font-size:1em; }}
.message.success {{ background:#1b4332; color:#95d5b2; border:1px solid #2d6a4f; }}
.message.error {{ background:#4a1525; color:#f4978e; border:1px solid #7a2040; }}
.preview {{ margin:15px auto; max-width:100%; max-height:200px; display:none; }}
.preview img {{ max-width:100%; max-height:200px; object-fit:contain; border-radius:8px; }}
.admin-link {{ margin-top:30px; }}
.admin-link a {{ color:#555; font-size:0.85em; text-decoration:none; }}
.admin-link a:hover {{ color:#e94560; }}
</style>
</head>
<body>
<div class="container">
  {logo_html}
  <h1>{title}</h1>
  <p class="greeting">{greeting}</p>
  {message_html}
  <form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">
    <div class="upload-area" id="dropZone">
      <label class="btn btn-select" for="fileInput">Bild auswaehlen</label>
      <input type="file" name="image" id="fileInput" accept="image/*">
      <p class="file-name" id="fileName">Oder Bild hierher ziehen</p>
      <div class="preview" id="preview"><img id="previewImg" src="" alt="Vorschau"></div>
    </div>
    <button type="submit" class="btn" id="uploadBtn" disabled>Hochladen</button>
  </form>
  <div class="admin-link"><a href="/admin">Admin</a></div>
</div>
<script>
const fi=document.getElementById('fileInput'),fn=document.getElementById('fileName'),
  ub=document.getElementById('uploadBtn'),dz=document.getElementById('dropZone'),
  pv=document.getElementById('preview'),pi=document.getElementById('previewImg');
function hf(f){{if(f){{fn.textContent=f.name;ub.disabled=false;
  if(f.type.startsWith('image/')){{const r=new FileReader();
  r.onload=function(e){{pi.src=e.target.result;pv.style.display='block';}};r.readAsDataURL(f);}}}}}}
fi.addEventListener('change',function(){{hf(this.files[0]);}});
dz.addEventListener('dragover',function(e){{e.preventDefault();this.classList.add('dragover');}});
dz.addEventListener('dragleave',function(){{this.classList.remove('dragover');}});
dz.addEventListener('drop',function(e){{e.preventDefault();this.classList.remove('dragover');
  if(e.dataTransfer.files.length){{fi.files=e.dataTransfer.files;hf(e.dataTransfer.files[0]);}}}});
</script>
</body></html>"""

# ---------------------------------------------------------------------------
# Login page HTML
# ---------------------------------------------------------------------------

HTML_LOGIN = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#1a1a2e; color:#eee; min-height:100vh;
  display:flex; justify-content:center; align-items:center; }}
.login-box {{ background:#16213e; padding:40px; border-radius:12px; width:340px; text-align:center; }}
h1 {{ font-size:1.5em; margin-bottom:20px; color:#e94560; }}
input[type="password"] {{ width:100%; padding:12px; border:1px solid #333; border-radius:8px;
  background:#0f3460; color:#eee; font-size:1em; margin-bottom:15px; outline:none; }}
input[type="password"]:focus {{ border-color:#e94560; }}
.btn {{ display:inline-block; background:#e94560; color:#fff; border:none; width:100%;
  padding:14px; font-size:1.1em; border-radius:8px; cursor:pointer; }}
.btn:hover {{ background:#c73a52; }}
.message {{ padding:10px; border-radius:8px; margin-bottom:15px; font-size:0.9em; }}
.message.error {{ background:#4a1525; color:#f4978e; border:1px solid #7a2040; }}
a {{ color:#aaa; font-size:0.85em; text-decoration:none; display:block; margin-top:15px; }}
a:hover {{ color:#e94560; }}
</style>
</head>
<body>
<div class="login-box">
  <h1>Admin Login</h1>
  {message_html}
  <form method="POST" action="/admin/login">
    <input type="password" name="password" placeholder="Passwort" autofocus>
    <button type="submit" class="btn">Anmelden</button>
  </form>
  <a href="/">Zurueck zur Startseite</a>
</div>
</body></html>"""

# ---------------------------------------------------------------------------
# Admin page HTML
# ---------------------------------------------------------------------------

HTML_ADMIN = """<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin - RPI Picture Show</title>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:#1a1a2e; color:#eee; min-height:100vh; padding:20px; }}
.container {{ max-width:900px; margin:0 auto; }}
.header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:25px; }}
.header h1 {{ color:#e94560; font-size:1.6em; }}
.header-links a {{ color:#aaa; text-decoration:none; margin-left:15px; font-size:0.9em; }}
.header-links a:hover {{ color:#e94560; }}
.tabs {{ display:flex; gap:5px; margin-bottom:20px; flex-wrap:wrap; }}
.tab {{ padding:10px 20px; background:#16213e; border:none; color:#aaa; cursor:pointer;
  border-radius:8px 8px 0 0; font-size:0.95em; }}
.tab.active {{ background:#0f3460; color:#e94560; }}
.tab:hover {{ color:#eee; }}
.panel {{ display:none; background:#16213e; padding:25px; border-radius:0 8px 8px 8px; }}
.panel.active {{ display:block; }}
.message {{ padding:12px 20px; border-radius:8px; margin-bottom:20px; font-size:0.95em; }}
.message.success {{ background:#1b4332; color:#95d5b2; border:1px solid #2d6a4f; }}
.message.error {{ background:#4a1525; color:#f4978e; border:1px solid #7a2040; }}
label {{ display:block; color:#aaa; font-size:0.9em; margin-bottom:4px; margin-top:12px; }}
input[type="number"], input[type="password"] {{
  width:100%; max-width:300px; padding:10px; border:1px solid #333; border-radius:6px;
  background:#0f3460; color:#eee; font-size:1em; }}
input[type="checkbox"] {{ width:auto; margin-right:8px; accent-color:#e94560; }}
.checkbox-row {{ display:flex; align-items:center; margin-top:12px; }}
.checkbox-row label {{ margin:0; }}
.section-title {{ color:#e94560; font-size:1.05em; margin-top:20px; margin-bottom:5px;
  padding-top:15px; border-top:1px solid #333; }}
input:focus {{ border-color:#e94560; outline:none; }}
.btn {{ display:inline-block; background:#e94560; color:#fff; border:none;
  padding:10px 24px; font-size:0.95em; border-radius:6px; cursor:pointer;
  margin-top:15px; text-decoration:none; }}
.btn:hover {{ background:#c73a52; }}
.btn-sm {{ padding:6px 14px; font-size:0.85em; margin-top:0; }}
.btn-danger {{ background:#7a2040; }}
.btn-danger:hover {{ background:#a02050; }}
.btn-secondary {{ background:#0f3460; }}
.btn-secondary:hover {{ background:#1a4a7a; }}
.gallery {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
  gap:12px; margin-top:15px; }}
.gallery-item {{ background:#0f3460; border-radius:8px; overflow:hidden; position:relative; }}
.gallery-item img {{ width:100%; height:120px; object-fit:cover; display:block; }}
.gallery-item .name {{ padding:6px 8px; font-size:0.75em; color:#aaa;
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.gallery-item .actions {{ padding:4px 8px 8px; }}
.upload-section {{ margin-top:20px; padding-top:15px; border-top:1px solid #333; }}
.upload-section input[type="file"] {{ color:#aaa; font-size:0.9em; }}
.empty {{ color:#555; font-style:italic; padding:20px; text-align:center; }}
.trash-header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>Admin Panel</h1>
    <div class="header-links">
      <a href="/">Upload-Seite</a>
      <a href="/admin/logout">Abmelden</a>
    </div>
  </div>

  {message_html}

  <div class="tabs">
    <button class="tab active" onclick="showTab('settings')">Einstellungen</button>
    <button class="tab" onclick="showTab('logos')">Logos</button>
    <button class="tab" onclick="showTab('pictures')">Bilder</button>
    <button class="tab" onclick="showTab('trash')">Papierkorb</button>
    <button class="tab" onclick="showTab('password')">Passwort</button>
  </div>

  <!-- Settings -->
  <div class="panel active" id="panel-settings">
    <form method="POST" action="/admin/settings">
      <label for="logo_sec">Logo-Anzeigedauer (Sekunden)</label>
      <input type="number" name="logo_display_seconds" id="logo_sec"
             value="{logo_display_seconds}" min="1" max="999" step="1">
      <label for="pics_sec">Bilder-Anzeigedauer (Sekunden)</label>
      <input type="number" name="pictures_display_seconds" id="pics_sec"
             value="{pictures_display_seconds}" min="1" max="999" step="1">
      <label for="up_sec">Upload-Anzeigedauer (Sekunden)</label>
      <input type="number" name="uploaded_display_seconds" id="up_sec"
             value="{uploaded_display_seconds}" min="1" max="999" step="1">
      <label for="trash_days">Papierkorb leeren nach (Tagen, 0 = nie)</label>
      <input type="number" name="delete_after_days" id="trash_days"
             value="{delete_after_days}" min="0" max="9999" step="1">

      <div class="section-title">Speicherplatz</div>
      <label for="min_free">Mindest-Freispeicher fuer Uploads (MB)</label>
      <input type="number" name="min_free_space_mb" id="min_free"
             value="{min_free_space_mb}" min="0" max="99999" step="10">
      <p style="color:#666;font-size:0.8em;margin-top:4px;">Aktuell frei: {free_space_mb} MB</p>

      <div class="section-title">Uebergangs-Dauer</div>
      <label for="dur_min">Minimale Dauer (ms)</label>
      <input type="number" name="transition_duration_min_ms" id="dur_min"
             value="{transition_duration_min_ms}" min="0" max="5000" step="50">
      <label for="dur_max">Maximale Dauer (ms)</label>
      <input type="number" name="transition_duration_max_ms" id="dur_max"
             value="{transition_duration_max_ms}" min="0" max="5000" step="50">
      <div class="checkbox-row">
        <input type="checkbox" name="transition_duration_random" id="dur_rnd"
               value="true" {transition_duration_random_checked}>
        <label for="dur_rnd">Zufaellige Dauer zwischen Min und Max</label>
      </div>
      <br>
      <button type="submit" class="btn">Speichern</button>
    </form>
  </div>

  <!-- Logos -->
  <div class="panel" id="panel-logos">
    <h3 style="color:#e94560;margin-bottom:5px;">Logo-Bilder</h3>
    {logos_gallery}
    <div class="upload-section">
      <form method="POST" action="/admin/upload/logo" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" required>
        <button type="submit" class="btn btn-sm btn-secondary">Logo hochladen</button>
      </form>
    </div>
  </div>

  <!-- Pictures -->
  <div class="panel" id="panel-pictures">
    <h3 style="color:#e94560;margin-bottom:5px;">Bilder</h3>
    {pictures_gallery}
    <div class="upload-section">
      <form method="POST" action="/admin/upload/pictures" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" required>
        <button type="submit" class="btn btn-sm btn-secondary">Bild hochladen</button>
      </form>
    </div>
  </div>

  <!-- Trash -->
  <div class="panel" id="panel-trash">
    <div class="trash-header">
      <h3 style="color:#e94560;">Papierkorb</h3>
      {trash_clear_btn}
    </div>
    {trash_gallery}
  </div>

  <!-- Password -->
  <div class="panel" id="panel-password">
    <form method="POST" action="/admin/password">
      <label for="old_pw">Aktuelles Passwort</label>
      <input type="password" name="old_password" id="old_pw" required>
      <label for="new_pw">Neues Passwort</label>
      <input type="password" name="new_password" id="new_pw" required>
      <label for="new_pw2">Neues Passwort wiederholen</label>
      <input type="password" name="new_password2" id="new_pw2" required>
      <br>
      <button type="submit" class="btn">Passwort aendern</button>
    </form>
  </div>
</div>

<script>
function showTab(name) {{
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById('panel-'+name).classList.add('active');
  event.target.classList.add('active');
}}
function confirmDelete(form, name) {{
  if(confirm('Bild "'+name+'" wirklich loeschen?')) form.submit();
}}
function confirmClearTrash() {{
  if(confirm('Gesamten Papierkorb leeren?')) document.getElementById('clearTrashForm').submit();
}}
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_path: str | None = None) -> Flask:
    config_file = config_path or get_config_path()
    cfg = load_config(config_file)

    base = cfg.get("paths", "base_path", fallback="/home/pi/slideshow")
    logo_folder_name = cfg.get("paths", "logo_folder", fallback="logo")
    pics_folder_name = cfg.get("paths", "pictures_folder", fallback="pictures")
    uploaded_folder_name = cfg.get("paths", "uploaded_folder", fallback="uploaded")
    trash_folder_name = cfg.get("paths", "trash_folder", fallback="trash")

    folder_map = {
        "logo": os.path.join(base, logo_folder_name),
        "pictures": os.path.join(base, pics_folder_name),
        "uploaded": os.path.join(base, uploaded_folder_name),
        "trash": os.path.join(base, trash_folder_name),
    }
    for d in folder_map.values():
        os.makedirs(d, exist_ok=True)

    title = cfg.get("web", "title", fallback="RPI Picture Show")
    greeting = cfg.get("web", "greeting", fallback="Willkommen! Laden Sie hier Ihre Bilder hoch.")

    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB

    # ---------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------

    def reload_cfg() -> configparser.ConfigParser:
        return load_config(config_file)

    def get_logo_html() -> str:
        logo_dir = folder_map["logo"]
        if not os.path.isdir(logo_dir):
            return ""
        logos = [
            os.path.join(logo_dir, f)
            for f in os.listdir(logo_dir)
            if f.lower().endswith(SUPPORTED_EXTENSIONS) and os.path.isfile(os.path.join(logo_dir, f))
        ]
        if not logos:
            return ""
        logo_path = random.choice(logos)
        ext = os.path.splitext(logo_path)[1].lower().lstrip(".")
        mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "bmp": "bmp", "gif": "gif"}.get(ext, "jpeg")
        try:
            with open(logo_path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return f'<div class="logo"><img src="data:image/{mime};base64,{data}" alt="Logo"></div>'
        except OSError:
            return ""

    def allowed_file(filename: str) -> bool:
        return filename.lower().endswith(SUPPORTED_EXTENSIONS)

    def list_images(folder_key: str) -> list[str]:
        d = folder_map.get(folder_key, "")
        if not os.path.isdir(d):
            return []
        return sorted(
            f for f in os.listdir(d)
            if f.lower().endswith(SUPPORTED_EXTENSIONS) and os.path.isfile(os.path.join(d, f))
        )

    def check_free_space() -> bool:
        """Return True if enough free space is available for upload."""
        current_cfg = reload_cfg()
        min_mb = current_cfg.getint("web", "min_free_space_mb", fallback=100)
        free_mb = get_free_space_mb(base)
        if free_mb < min_mb:
            log.warning("Nicht genug Speicherplatz: %d MB frei, %d MB benoetigt", free_mb, min_mb)
            return False
        return True

    def build_gallery(folder_key: str, show_delete: bool = True) -> str:
        images = list_images(folder_key)
        if not images:
            return '<div class="empty">Keine Bilder vorhanden.</div>'
        items = []
        for img_name in images:
            img_url = f"/admin/image/{folder_key}/{img_name}"
            delete_html = ""
            if show_delete:
                delete_html = (
                    f'<form method="POST" action="/admin/delete/{folder_key}/{img_name}" '
                    f'style="display:inline" onsubmit="event.preventDefault();'
                    f'confirmDelete(this,\'{img_name}\');">'
                    f'<button type="submit" class="btn btn-sm btn-danger">Loeschen</button></form>'
                )
            items.append(
                f'<div class="gallery-item">'
                f'<img src="{img_url}" alt="{img_name}" loading="lazy">'
                f'<div class="name" title="{img_name}">{img_name}</div>'
                f'<div class="actions">{delete_html}</div></div>'
            )
        return '<div class="gallery">' + "".join(items) + '</div>'

    def msg_html(msg: str, msg_type: str = "success") -> str:
        if not msg:
            return ""
        return f'<div class="message {msg_type}">{msg}</div>'

    def require_admin(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("admin"):
                return redirect(url_for("admin_login"))
            return f(*args, **kwargs)
        return wrapper

    # ---------------------------------------------------------------
    # Public routes
    # ---------------------------------------------------------------

    @app.route("/")
    def index():
        msg = request.args.get("msg", "")
        msg_type = request.args.get("type", "success")
        html = HTML_UPLOAD.format(
            title=title, greeting=greeting,
            logo_html=get_logo_html(),
            message_html=msg_html(msg, msg_type),
        )
        return Response(html, mimetype="text/html")

    @app.route("/upload", methods=["POST"])
    def upload():
        if "image" not in request.files:
            return redirect(url_for("index", msg="Keine Datei ausgewaehlt.", type="error"))
        file = request.files["image"]
        if file.filename == "":
            return redirect(url_for("index", msg="Keine Datei ausgewaehlt.", type="error"))
        if not allowed_file(file.filename):
            return redirect(url_for("index", msg="Nicht unterstuetztes Dateiformat.", type="error"))
        if not check_free_space():
            return redirect(url_for("index", msg="Nicht genug Speicherplatz!", type="error"))
        filename = make_timestamped_name(secure_filename(file.filename))
        dest = os.path.join(folder_map["uploaded"], filename)
        file.save(dest)
        client_ip = request.remote_addr
        log.info("Upload: %s von IP %s", filename, client_ip)
        return redirect(url_for("index", msg=f"Bild '{filename}' erfolgreich hochgeladen!", type="success"))

    # ---------------------------------------------------------------
    # Auth routes
    # ---------------------------------------------------------------

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "GET":
            if session.get("admin"):
                return redirect(url_for("admin_dashboard"))
            return Response(HTML_LOGIN.format(message_html=""), mimetype="text/html")

        password = request.form.get("password", "")
        current_cfg = reload_cfg()
        stored_hash = current_cfg.get("admin", "password_hash", fallback="")
        if hash_password(password) == stored_hash:
            session["admin"] = True
            log.info("Admin-Login erfolgreich")
            return redirect(url_for("admin_dashboard"))
        log.warning("Admin-Login fehlgeschlagen")
        return Response(
            HTML_LOGIN.format(message_html=msg_html("Falsches Passwort.", "error")),
            mimetype="text/html",
        )

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("admin", None)
        return redirect(url_for("index"))

    # ---------------------------------------------------------------
    # Admin dashboard
    # ---------------------------------------------------------------

    @app.route("/admin")
    @require_admin
    def admin_dashboard():
        current_cfg = reload_cfg()
        msg = request.args.get("msg", "")
        msg_type = request.args.get("type", "success")

        trash_images = list_images("trash")
        trash_clear = ""
        if trash_images:
            trash_clear = (
                '<form method="POST" action="/admin/trash/clear" id="clearTrashForm" '
                'style="display:inline">'
                '<button type="button" class="btn btn-sm btn-danger" '
                'onclick="confirmClearTrash()">Alle loeschen</button></form>'
            )

        dur_random = current_cfg.getboolean("display", "transition_duration_random", fallback=False)

        html = HTML_ADMIN.format(
            message_html=msg_html(msg, msg_type),
            logo_display_seconds=current_cfg.getint("timing", "logo_display_seconds", fallback=10),
            pictures_display_seconds=current_cfg.getint("timing", "pictures_display_seconds", fallback=10),
            uploaded_display_seconds=current_cfg.getint("timing", "uploaded_display_seconds", fallback=10),
            delete_after_days=current_cfg.getint("trash", "delete_after_days", fallback=30),
            transition_duration_min_ms=current_cfg.getint("display", "transition_duration_min_ms", fallback=300),
            transition_duration_max_ms=current_cfg.getint("display", "transition_duration_max_ms", fallback=800),
            transition_duration_random_checked="checked" if dur_random else "",
            min_free_space_mb=current_cfg.getint("web", "min_free_space_mb", fallback=100),
            free_space_mb=get_free_space_mb(base),
            logos_gallery=build_gallery("logo"),
            pictures_gallery=build_gallery("pictures"),
            trash_gallery=build_gallery("trash"),
            trash_clear_btn=trash_clear,
        )
        return Response(html, mimetype="text/html")

    # ---------------------------------------------------------------
    # Admin actions
    # ---------------------------------------------------------------

    @app.route("/admin/settings", methods=["POST"])
    @require_admin
    def admin_settings():
        current_cfg = reload_cfg()
        for key in ("logo_display_seconds", "pictures_display_seconds", "uploaded_display_seconds"):
            val = request.form.get(key, "")
            if val.isdigit() and int(val) >= 1:
                if not current_cfg.has_section("timing"):
                    current_cfg.add_section("timing")
                current_cfg.set("timing", key, val)
        trash_days = request.form.get("delete_after_days", "")
        if trash_days.isdigit():
            if not current_cfg.has_section("trash"):
                current_cfg.add_section("trash")
            current_cfg.set("trash", "delete_after_days", trash_days)
        # Min free space
        min_free = request.form.get("min_free_space_mb", "")
        if min_free.isdigit():
            if not current_cfg.has_section("web"):
                current_cfg.add_section("web")
            current_cfg.set("web", "min_free_space_mb", min_free)
        # Transition duration
        if not current_cfg.has_section("display"):
            current_cfg.add_section("display")
        for key in ("transition_duration_min_ms", "transition_duration_max_ms"):
            val = request.form.get(key, "")
            if val.isdigit():
                current_cfg.set("display", key, val)
        dur_random = "true" if request.form.get("transition_duration_random") else "false"
        current_cfg.set("display", "transition_duration_random", dur_random)
        save_config(current_cfg, config_file)
        log.info("Einstellungen gespeichert")
        return redirect(url_for("admin_dashboard", msg="Einstellungen gespeichert.", type="success"))

    @app.route("/admin/upload/<folder>", methods=["POST"])
    @require_admin
    def admin_upload(folder):
        if folder not in ("logo", "pictures"):
            return redirect(url_for("admin_dashboard", msg="Ungueltiger Ordner.", type="error"))
        if "image" not in request.files:
            return redirect(url_for("admin_dashboard", msg="Keine Datei ausgewaehlt.", type="error"))
        file = request.files["image"]
        if file.filename == "" or not allowed_file(file.filename):
            return redirect(url_for("admin_dashboard", msg="Ungueltige Datei.", type="error"))
        if not check_free_space():
            return redirect(url_for("admin_dashboard", msg="Nicht genug Speicherplatz!", type="error"))
        filename = make_timestamped_name(secure_filename(file.filename))
        dest = os.path.join(folder_map[folder], filename)
        file.save(dest)
        client_ip = request.remote_addr
        log.info("Admin-Upload: %s -> %s/ von IP %s", filename, folder, client_ip)
        return redirect(url_for("admin_dashboard", msg=f"'{filename}' hochgeladen in {folder}/.", type="success"))

    @app.route("/admin/delete/<folder>/<filename>", methods=["POST"])
    @require_admin
    def admin_delete(folder, filename):
        if folder not in ALLOWED_FOLDERS:
            return redirect(url_for("admin_dashboard", msg="Ungueltiger Ordner.", type="error"))
        filename = secure_filename(filename)
        filepath = os.path.join(folder_map[folder], filename)
        if os.path.isfile(filepath):
            os.remove(filepath)
            log.info("Admin-Loeschung: %s/%s", folder, filename)
            return redirect(url_for("admin_dashboard", msg=f"'{filename}' geloescht.", type="success"))
        return redirect(url_for("admin_dashboard", msg="Datei nicht gefunden.", type="error"))

    @app.route("/admin/trash/clear", methods=["POST"])
    @require_admin
    def admin_trash_clear():
        trash_dir = folder_map["trash"]
        count = 0
        for f in os.listdir(trash_dir):
            fp = os.path.join(trash_dir, f)
            if os.path.isfile(fp):
                os.remove(fp)
                count += 1
        log.info("Papierkorb geleert: %d Dateien", count)
        return redirect(url_for("admin_dashboard", msg=f"Papierkorb geleert ({count} Dateien).", type="success"))

    @app.route("/admin/password", methods=["POST"])
    @require_admin
    def admin_password():
        current_cfg = reload_cfg()
        stored_hash = current_cfg.get("admin", "password_hash", fallback="")
        old_pw = request.form.get("old_password", "")
        new_pw = request.form.get("new_password", "")
        new_pw2 = request.form.get("new_password2", "")

        if hash_password(old_pw) != stored_hash:
            return redirect(url_for("admin_dashboard", msg="Aktuelles Passwort ist falsch.", type="error"))
        if not new_pw or len(new_pw) < 4:
            return redirect(url_for("admin_dashboard", msg="Neues Passwort muss mindestens 4 Zeichen haben.", type="error"))
        if new_pw != new_pw2:
            return redirect(url_for("admin_dashboard", msg="Neue Passwoerter stimmen nicht ueberein.", type="error"))

        if not current_cfg.has_section("admin"):
            current_cfg.add_section("admin")
        current_cfg.set("admin", "password_hash", hash_password(new_pw))
        save_config(current_cfg, config_file)
        log.info("Admin-Passwort geaendert")
        return redirect(url_for("admin_dashboard", msg="Passwort erfolgreich geaendert.", type="success"))

    @app.route("/admin/image/<folder>/<filename>")
    @require_admin
    def admin_image(folder, filename):
        if folder not in ALLOWED_FOLDERS:
            return Response("Not found", status=404)
        filename = secure_filename(filename)
        return send_from_directory(folder_map[folder], filename)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_config(config_path or get_config_path())
    port = cfg.getint("web", "port", fallback=8080)

    app = create_app(config_path)
    log.info("Starte Web-Upload auf Port %d ...", port)
    app.run(host="0.0.0.0", port=port, debug=False)


if __name__ == "__main__":
    main()
