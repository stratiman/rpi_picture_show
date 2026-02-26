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
import json
import logging
import os
import random
import shutil
import subprocess
import sys
import threading
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
RESCAN_TRIGGER = "/tmp/rpi-slideshow-rescan"

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


def get_version() -> str:
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
    try:
        with open(version_file) as f:
            return f.read().strip()
    except OSError:
        return "?"


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


def file_exists_in_folder(folder: str, original_filename: str) -> bool:
    """Check if a file with the same base name already exists (ignoring timestamp suffix)."""
    name, ext = os.path.splitext(original_filename)
    ext_lower = ext.lower()
    for existing in os.listdir(folder):
        ex_name, ex_ext = os.path.splitext(existing)
        if ex_ext.lower() != ext_lower:
            continue
        # Match exact name or name with timestamp suffix (name_YYYYMMDD_HHMMSS)
        if ex_name == name or ex_name.startswith(name + "_"):
            return True
    return False


UPLOAD_LOG_MAX_DEFAULT = 200


def get_upload_log_path(config_path: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config_path)), "upload_log.json")


def load_upload_log(log_path: str) -> list[dict]:
    if not os.path.isfile(log_path):
        return []
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return []


def save_upload_log(log_path: str, entries: list[dict], max_entries: int = UPLOAD_LOG_MAX_DEFAULT):
    entries = entries[-max_entries:]
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)


def log_upload_entry(log_path: str, filename: str, folder: str, ip: str,
                     max_entries: int = UPLOAD_LOG_MAX_DEFAULT):
    entries = load_upload_log(log_path)
    entries.append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "file": filename,
        "folder": folder,
        "ip": ip,
    })
    save_upload_log(log_path, entries, max_entries)


# ---------------------------------------------------------------------------
# Upload page HTML
# ---------------------------------------------------------------------------

HTML_UPLOAD = """<!DOCTYPE html>
<html lang="de" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
:root[data-theme="dark"] {{
  --bg: #1a1a2e; --fg: #eee; --muted: #aaa; --card: #16213e; --card-hover: #1a1a3e;
  --card-active: #1f2b4d; --input-bg: #0f3460; --accent: #e94560; --accent-hover: #c73a52;
  --accent-light: #ff6b81; --link-muted: #555;
  --msg-ok-bg: #1b4332; --msg-ok-fg: #95d5b2; --msg-ok-border: #2d6a4f;
  --msg-err-bg: #4a1525; --msg-err-fg: #f4978e; --msg-err-border: #7a2040;
}}
:root[data-theme="light"] {{
  --bg: #f0f2f5; --fg: #222; --muted: #555; --card: #fff; --card-hover: #f5f5f5;
  --card-active: #e8ecf0; --input-bg: #e8ecf0; --accent: #d63851; --accent-hover: #b82e44;
  --accent-light: #e94560; --link-muted: #888;
  --msg-ok-bg: #d4edda; --msg-ok-fg: #155724; --msg-ok-border: #c3e6cb;
  --msg-err-bg: #f8d7da; --msg-err-fg: #721c24; --msg-err-border: #f5c6cb;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg); color:var(--fg); min-height:100vh;
  display:flex; flex-direction:column; align-items:center; padding:20px; transition:background 0.3s,color 0.3s; }}
.container {{ max-width:600px; width:100%; text-align:center; }}
.theme-toggle {{ position:fixed; top:15px; right:15px; background:var(--card); border:1px solid var(--muted);
  color:var(--fg); width:40px; height:40px; border-radius:50%; cursor:pointer; font-size:1.2em;
  display:flex; align-items:center; justify-content:center; transition:background 0.3s; z-index:100; }}
.theme-toggle:hover {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.logo {{ margin:20px auto; max-width:280px; max-height:200px; }}
.logo img {{ max-width:100%; max-height:200px; object-fit:contain; border-radius:8px; }}
h1 {{ font-size:1.8em; margin-bottom:10px; color:var(--accent); }}
.greeting {{ font-size:1.1em; color:var(--muted); margin-bottom:30px; line-height:1.5; }}
.upload-area {{ background:var(--card); border:2px dashed var(--accent); border-radius:12px;
  padding:40px 20px; margin-bottom:20px; transition:background 0.2s; }}
.upload-area:hover {{ background:var(--card-hover); }}
.upload-area.dragover {{ background:var(--card-active); border-color:var(--accent-light); }}
input[type="file"] {{ display:none; }}
.btn {{ display:inline-block; background:var(--accent); color:#fff; border:none;
  padding:14px 32px; font-size:1.1em; border-radius:8px; cursor:pointer;
  transition:background 0.2s; text-decoration:none; }}
.btn:hover {{ background:var(--accent-hover); }}
.btn:disabled {{ background:#555; cursor:not-allowed; }}
.btn-select {{ background:var(--input-bg); color:var(--fg); margin-bottom:15px; }}
.btn-select:hover {{ background:var(--card-active); }}
.file-name {{ margin:10px 0; font-size:0.95em; color:var(--muted); min-height:1.4em; }}
.message {{ padding:12px 20px; border-radius:8px; margin-bottom:20px; font-size:1em; }}
.message.success {{ background:var(--msg-ok-bg); color:var(--msg-ok-fg); border:1px solid var(--msg-ok-border); }}
.message.error {{ background:var(--msg-err-bg); color:var(--msg-err-fg); border:1px solid var(--msg-err-border); }}
.preview {{ margin:15px auto; max-width:100%; display:none; }}
.preview img {{ max-width:120px; max-height:120px; object-fit:contain; border-radius:6px; }}
.admin-link {{ margin-top:30px; }}
.admin-link a {{ color:var(--link-muted); font-size:0.85em; text-decoration:none; }}
.admin-link a:hover {{ color:var(--accent); }}
.version {{ color:var(--link-muted); font-size:0.75em; margin-top:10px; }}
</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="Theme wechseln"></button>
<div class="container">
  {logo_html}
  <h1>{title}</h1>
  <p class="greeting">{greeting}</p>
  {message_html}
  <form method="POST" action="/upload" enctype="multipart/form-data" id="uploadForm">
    <div class="upload-area" id="dropZone">
      <label class="btn btn-select" for="fileInput">Bilder auswaehlen</label>
      <input type="file" name="image" id="fileInput" accept="image/*" multiple>
      <p class="file-name" id="fileName">Oder Bilder hierher ziehen</p>
      <div class="preview" id="preview"></div>
    </div>
    <button type="submit" class="btn" id="uploadBtn" disabled>Hochladen</button>
  </form>
  <div class="admin-link"><a href="/admin">Admin</a></div>
  <div class="version">v{version}</div>
</div>
<script>
(function(){{
  const tb=document.getElementById('themeToggle'),root=document.documentElement;
  function setTheme(t){{root.setAttribute('data-theme',t);localStorage.setItem('theme',t);
    tb.textContent=t==='dark'?'\\u2600\\ufe0f':'\\ud83c\\udf19';}}
  setTheme(localStorage.getItem('theme')||'dark');
  tb.addEventListener('click',function(){{setTheme(root.getAttribute('data-theme')==='dark'?'light':'dark');}});
}})();
const fi=document.getElementById('fileInput'),fn=document.getElementById('fileName'),
  ub=document.getElementById('uploadBtn'),dz=document.getElementById('dropZone'),
  pv=document.getElementById('preview'),maxBytes={max_upload_mb}*1024*1024;
function showFiles(files){{
  if(!files||!files.length)return;
  const n=files.length;
  let total=0;
  for(let i=0;i<n;i++)total+=files[i].size;
  const totalMB=(total/1024/1024).toFixed(1);
  if(total>maxBytes){{
    fn.textContent=n+' Bilder ('+totalMB+' MB) - zu gross! Max: {max_upload_mb} MB';
    fn.style.color='var(--msg-err-fg)';
    ub.disabled=true;
    pv.innerHTML='';pv.style.display='none';
    return;
  }}
  fn.style.color='';
  fn.textContent=n===1?files[0].name+' ('+totalMB+' MB)':n+' Bilder ('+totalMB+' MB)';
  ub.disabled=false;
  pv.innerHTML='';pv.style.display='flex';pv.style.flexWrap='wrap';
  pv.style.gap='8px';pv.style.justifyContent='center';
  const max=8;
  for(let i=0;i<Math.min(n,max);i++){{
    if(files[i].type.startsWith('image/')){{
      const img=document.createElement('img');
      img.style.maxWidth='120px';img.style.maxHeight='120px';
      img.style.objectFit='contain';img.style.borderRadius='6px';
      const r=new FileReader();
      r.onload=function(e){{img.src=e.target.result;}};
      r.readAsDataURL(files[i]);pv.appendChild(img);
    }}
  }}
  if(n>max){{const s=document.createElement('span');s.style.color='var(--muted)';
    s.style.alignSelf='center';s.textContent='+'+(n-max)+' weitere';pv.appendChild(s);}}
}}
fi.addEventListener('change',function(){{showFiles(this.files);}});
dz.addEventListener('dragover',function(e){{e.preventDefault();this.classList.add('dragover');}});
dz.addEventListener('dragleave',function(){{this.classList.remove('dragover');}});
dz.addEventListener('drop',function(e){{e.preventDefault();this.classList.remove('dragover');
  if(e.dataTransfer.files.length){{fi.files=e.dataTransfer.files;showFiles(e.dataTransfer.files);}}}});
</script>
</body></html>"""

# ---------------------------------------------------------------------------
# Login page HTML
# ---------------------------------------------------------------------------

HTML_LOGIN = """<!DOCTYPE html>
<html lang="de" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin Login</title>
<style>
:root[data-theme="dark"] {{
  --bg: #1a1a2e; --fg: #eee; --muted: #aaa; --card: #16213e;
  --input-bg: #0f3460; --accent: #e94560; --accent-hover: #c73a52;
  --msg-err-bg: #4a1525; --msg-err-fg: #f4978e; --msg-err-border: #7a2040;
}}
:root[data-theme="light"] {{
  --bg: #f0f2f5; --fg: #222; --muted: #555; --card: #fff;
  --input-bg: #e8ecf0; --accent: #d63851; --accent-hover: #b82e44;
  --msg-err-bg: #f8d7da; --msg-err-fg: #721c24; --msg-err-border: #f5c6cb;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg); color:var(--fg); min-height:100vh;
  display:flex; justify-content:center; align-items:center; transition:background 0.3s,color 0.3s; }}
.theme-toggle {{ position:fixed; top:15px; right:15px; background:var(--card); border:1px solid var(--muted);
  color:var(--fg); width:40px; height:40px; border-radius:50%; cursor:pointer; font-size:1.2em;
  display:flex; align-items:center; justify-content:center; transition:background 0.3s; z-index:100; }}
.theme-toggle:hover {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.login-box {{ background:var(--card); padding:40px; border-radius:12px; width:340px; text-align:center; }}
h1 {{ font-size:1.5em; margin-bottom:20px; color:var(--accent); }}
input[type="password"] {{ width:100%; padding:12px; border:1px solid var(--muted); border-radius:8px;
  background:var(--input-bg); color:var(--fg); font-size:1em; margin-bottom:15px; outline:none; }}
input[type="password"]:focus {{ border-color:var(--accent); }}
.btn {{ display:inline-block; background:var(--accent); color:#fff; border:none; width:100%;
  padding:14px; font-size:1.1em; border-radius:8px; cursor:pointer; }}
.btn:hover {{ background:var(--accent-hover); }}
.message {{ padding:10px; border-radius:8px; margin-bottom:15px; font-size:0.9em; }}
.message.error {{ background:var(--msg-err-bg); color:var(--msg-err-fg); border:1px solid var(--msg-err-border); }}
a {{ color:var(--muted); font-size:0.85em; text-decoration:none; display:block; margin-top:15px; }}
a:hover {{ color:var(--accent); }}
</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="Theme wechseln"></button>
<div class="login-box">
  <h1>Admin Login</h1>
  {message_html}
  <form method="POST" action="/admin/login">
    <input type="password" name="password" placeholder="Passwort" autofocus>
    <button type="submit" class="btn">Anmelden</button>
  </form>
  <a href="/">Zurueck zur Startseite</a>
</div>
<script>
(function(){{
  const tb=document.getElementById('themeToggle'),root=document.documentElement;
  function setTheme(t){{root.setAttribute('data-theme',t);localStorage.setItem('theme',t);
    tb.textContent=t==='dark'?'\\u2600\\ufe0f':'\\ud83c\\udf19';}}
  setTheme(localStorage.getItem('theme')||'dark');
  tb.addEventListener('click',function(){{setTheme(root.getAttribute('data-theme')==='dark'?'light':'dark');}});
}})();
</script>
</body></html>"""

# ---------------------------------------------------------------------------
# Admin page HTML
# ---------------------------------------------------------------------------

HTML_ADMIN = """<!DOCTYPE html>
<html lang="de" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Admin - RPI Picture Show</title>
<style>
:root[data-theme="dark"] {{
  --bg: #1a1a2e; --fg: #eee; --muted: #aaa; --card: #16213e; --card-hover: #1a1a3e;
  --card-active: #1f2b4d; --input-bg: #0f3460; --input-border: #333;
  --accent: #e94560; --accent-hover: #c73a52; --link-muted: #555;
  --msg-ok-bg: #1b4332; --msg-ok-fg: #95d5b2; --msg-ok-border: #2d6a4f;
  --msg-err-bg: #4a1525; --msg-err-fg: #f4978e; --msg-err-border: #7a2040;
  --danger: #7a2040; --danger-hover: #a02050;
  --border: #333; --gallery-bg: #0f3460;
  --table-head: #0f3460; --table-stripe: #1a2340; --table-border: #2a3555;
}}
:root[data-theme="light"] {{
  --bg: #f0f2f5; --fg: #222; --muted: #555; --card: #fff; --card-hover: #f5f5f5;
  --card-active: #e8ecf0; --input-bg: #e8ecf0; --input-border: #ccc;
  --accent: #d63851; --accent-hover: #b82e44; --link-muted: #888;
  --msg-ok-bg: #d4edda; --msg-ok-fg: #155724; --msg-ok-border: #c3e6cb;
  --msg-err-bg: #f8d7da; --msg-err-fg: #721c24; --msg-err-border: #f5c6cb;
  --danger: #c0392b; --danger-hover: #e74c3c;
  --border: #ddd; --gallery-bg: #e8ecf0;
  --table-head: #e8ecf0; --table-stripe: #f5f5f5; --table-border: #ddd;
}}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg); color:var(--fg); min-height:100vh; padding:20px; transition:background 0.3s,color 0.3s; }}
.container {{ max-width:900px; margin:0 auto; }}
.theme-toggle {{ position:fixed; top:15px; right:15px; background:var(--card); border:1px solid var(--muted);
  color:var(--fg); width:40px; height:40px; border-radius:50%; cursor:pointer; font-size:1.2em;
  display:flex; align-items:center; justify-content:center; transition:background 0.3s; z-index:100; }}
.theme-toggle:hover {{ background:var(--accent); color:#fff; border-color:var(--accent); }}
.header {{ display:flex; justify-content:space-between; align-items:center; margin-bottom:25px; }}
.header h1 {{ color:var(--accent); font-size:1.6em; }}
.header-links a {{ color:var(--muted); text-decoration:none; margin-left:15px; font-size:0.9em; }}
.header-links a:hover {{ color:var(--accent); }}
.tabs {{ display:flex; gap:5px; margin-bottom:20px; flex-wrap:wrap; }}
.tab {{ padding:10px 20px; background:var(--card); border:none; color:var(--muted); cursor:pointer;
  border-radius:8px 8px 0 0; font-size:0.95em; }}
.tab.active {{ background:var(--input-bg); color:var(--accent); }}
.tab:hover {{ color:var(--fg); }}
.panel {{ display:none; background:var(--card); padding:25px; border-radius:0 8px 8px 8px; }}
.panel.active {{ display:block; }}
.message {{ padding:12px 20px; border-radius:8px; margin-bottom:20px; font-size:0.95em; }}
.message.success {{ background:var(--msg-ok-bg); color:var(--msg-ok-fg); border:1px solid var(--msg-ok-border); }}
.message.error {{ background:var(--msg-err-bg); color:var(--msg-err-fg); border:1px solid var(--msg-err-border); }}
label {{ display:block; color:var(--muted); font-size:0.9em; margin-bottom:4px; margin-top:12px; }}
input[type="number"], input[type="password"] {{
  width:100%; max-width:300px; padding:10px; border:1px solid var(--input-border); border-radius:6px;
  background:var(--input-bg); color:var(--fg); font-size:1em; }}
input[type="checkbox"] {{ width:auto; margin-right:8px; accent-color:var(--accent); }}
.checkbox-row {{ display:flex; align-items:center; margin-top:12px; }}
.checkbox-row label {{ margin:0; }}
.section-title {{ color:var(--accent); font-size:1.05em; margin-top:20px; margin-bottom:5px;
  padding-top:15px; border-top:1px solid var(--border); }}
input:focus {{ border-color:var(--accent); outline:none; }}
.btn {{ display:inline-block; background:var(--accent); color:#fff; border:none;
  padding:10px 24px; font-size:0.95em; border-radius:6px; cursor:pointer;
  margin-top:15px; text-decoration:none; }}
.btn:hover {{ background:var(--accent-hover); }}
.btn-sm {{ padding:6px 14px; font-size:0.85em; margin-top:0; }}
.btn-danger {{ background:var(--danger); }}
.btn-danger:hover {{ background:var(--danger-hover); }}
.btn-secondary {{ background:var(--input-bg); color:var(--fg); }}
.btn-secondary:hover {{ background:var(--card-active); }}
.gallery {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(140px,1fr));
  gap:12px; margin-top:15px; }}
.gallery-item {{ background:var(--gallery-bg); border-radius:8px; overflow:hidden; position:relative; }}
.gallery-item img {{ width:100%; height:120px; object-fit:cover; display:block; }}
.gallery-item .name {{ padding:6px 8px; font-size:0.75em; color:var(--muted);
  white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.gallery-item .actions {{ padding:4px 8px 8px; }}
.upload-section {{ margin-top:20px; padding-top:15px; border-top:1px solid var(--border); }}
.upload-section input[type="file"] {{ color:var(--muted); font-size:0.9em; }}
.empty {{ color:var(--link-muted); font-style:italic; padding:20px; text-align:center; }}
.trash-header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; }}
.log-table {{ width:100%; border-collapse:collapse; margin-top:10px; font-size:0.9em; }}
.log-table th {{ background:var(--table-head); color:var(--accent); padding:10px 12px;
  text-align:left; font-weight:600; border-bottom:2px solid var(--table-border); }}
.log-table td {{ padding:8px 12px; border-bottom:1px solid var(--table-border); color:var(--fg); }}
.log-table tr:nth-child(even) {{ background:var(--table-stripe); }}
.log-table tr:hover {{ background:var(--card-active); }}
.log-empty {{ color:var(--link-muted); font-style:italic; padding:20px; text-align:center; }}
.log-info {{ color:var(--muted); font-size:0.85em; margin-top:10px; }}
</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" title="Theme wechseln"></button>
<div class="container">
  <div class="header">
    <h1>Admin Panel <span style="font-size:0.45em;color:var(--muted);font-weight:normal;">v{version}</span></h1>
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
    <button class="tab" onclick="showTab('uploadlog')">Upload-Log</button>
    <button class="tab" onclick="showTab('password')">Passwort</button>
    <button class="tab" onclick="showTab('update')">Update</button>
    <button class="tab" onclick="showTab('system')">System</button>
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

      <div class="section-title">Upload-Log</div>
      <label for="log_max">Maximale Anzahl Log-Eintraege</label>
      <input type="number" name="upload_log_max" id="log_max"
             value="{upload_log_max}" min="10" max="10000" step="10">

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
    <h3 style="color:var(--accent);margin-bottom:5px;">Logo-Bilder</h3>
    {logos_gallery}
    <div class="upload-section">
      <form method="POST" action="/admin/upload/logo" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" multiple required>
        <button type="submit" class="btn btn-sm btn-secondary">Logo(s) hochladen</button>
      </form>
    </div>
  </div>

  <!-- Pictures -->
  <div class="panel" id="panel-pictures">
    <h3 style="color:var(--accent);margin-bottom:5px;">Bilder</h3>
    {pictures_gallery}
    <div class="upload-section">
      <form method="POST" action="/admin/upload/pictures" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" multiple required>
        <button type="submit" class="btn btn-sm btn-secondary">Bild(er) hochladen</button>
      </form>
    </div>
  </div>

  <!-- Trash -->
  <div class="panel" id="panel-trash">
    <div class="trash-header">
      <h3 style="color:var(--accent);">Papierkorb</h3>
      {trash_clear_btn}
    </div>
    {trash_gallery}
  </div>

  <!-- Upload Log -->
  <div class="panel" id="panel-uploadlog">
    <h3 style="color:var(--accent);margin-bottom:10px;">Upload-Log</h3>
    {upload_log_html}
    <p class="log-info">Es werden die letzten {upload_log_max} Eintraege angezeigt.</p>
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

  <!-- System -->
  <div class="panel" id="panel-system">
    <h3 style="color:var(--accent);margin-bottom:10px;">System</h3>
    <p style="margin-bottom:15px;">Slideshow- und Web-Service steuern oder das System herunterfahren.</p>
    <div style="display:flex;flex-wrap:wrap;gap:10px;">
      <button type="button" class="btn" onclick="systemAction('stop-slideshow','Slideshow stoppen?')">Slideshow stoppen</button>
      <button type="button" class="btn" onclick="systemAction('start-slideshow','Slideshow starten?')">Slideshow starten</button>
      <button type="button" class="btn" onclick="systemAction('restart-slideshow','Slideshow neu starten?')">Slideshow neustarten</button>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-top:15px;">
      <button type="button" class="btn" style="background:#c00;" onclick="systemAction('reboot','System wirklich neu starten?')">System neustarten</button>
      <button type="button" class="btn" style="background:#800;" onclick="systemAction('shutdown','System wirklich herunterfahren?')">System herunterfahren</button>
    </div>
    <div id="systemStatus" style="display:none;margin-top:15px;padding:12px;border-radius:6px;"></div>
  </div>

  <!-- Update -->
  <div class="panel" id="panel-update">
    <h3 style="color:var(--accent);margin-bottom:10px;">Software-Update</h3>
    <p>Aktuelle Version: <strong>v{version}</strong></p>
    <button type="button" class="btn" id="btnCheckUpdate" onclick="checkUpdate()">Auf Updates pruefen</button>
    <div id="updateResult" style="display:none;margin-top:15px;padding:12px;border-radius:6px;"></div>
    <div id="updateActions" style="display:none;margin-top:10px;">
      <button type="button" class="btn" onclick="doUpdate()">Jetzt aktualisieren</button>
    </div>
    <div id="updateStatus" style="display:none;margin-top:15px;padding:12px;border-radius:6px;"></div>
  </div>
</div>

<script>
(function(){{
  const tb=document.getElementById('themeToggle'),root=document.documentElement;
  function setTheme(t){{root.setAttribute('data-theme',t);localStorage.setItem('theme',t);
    tb.textContent=t==='dark'?'\\u2600\\ufe0f':'\\ud83c\\udf19';}}
  setTheme(localStorage.getItem('theme')||'dark');
  tb.addEventListener('click',function(){{setTheme(root.getAttribute('data-theme')==='dark'?'light':'dark');}});
}})();
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
function checkUpdate() {{
  var btn=document.getElementById('btnCheckUpdate');
  var res=document.getElementById('updateResult');
  var act=document.getElementById('updateActions');
  btn.disabled=true; btn.textContent='Pruefe ...';
  res.style.display='none'; act.style.display='none';
  fetch('/admin/check-update')
    .then(function(r){{ return r.json(); }})
    .then(function(d){{
      btn.disabled=false; btn.textContent='Auf Updates pruefen';
      res.style.display='block';
      if(d.error){{
        res.style.background='#fee'; res.style.color='#c00';
        res.textContent='Fehler: '+d.error;
      }} else if(d.update_available){{
        res.style.background='#efe'; res.style.color='#060';
        res.textContent='Update verfuegbar: v'+d.current+' \\u2192 v'+d.remote;
        act.style.display='block';
      }} else {{
        res.style.background='#eef'; res.style.color='#006';
        res.textContent='Kein Update verfuegbar. Version v'+d.current+' ist aktuell.';
      }}
    }})
    .catch(function(e){{
      btn.disabled=false; btn.textContent='Auf Updates pruefen';
      res.style.display='block'; res.style.background='#fee'; res.style.color='#c00';
      res.textContent='Verbindungsfehler: '+e.message;
    }});
}}
function doUpdate() {{
  var act=document.getElementById('updateActions');
  var st=document.getElementById('updateStatus');
  act.style.display='none';
  st.style.display='block'; st.style.background='#eef'; st.style.color='#006';
  st.textContent='Update wird durchgefuehrt ...';
  fetch('/admin/update',{{method:'POST'}})
    .then(function(r){{ return r.json(); }})
    .then(function(d){{
      if(d.error){{
        st.style.background='#fee'; st.style.color='#c00';
        st.textContent='Fehler: '+d.error;
      }} else {{
        st.style.background='#efe'; st.style.color='#060';
        st.innerHTML='Update auf v'+d.new_version+' erfolgreich!<br>Services werden neu gestartet. Seite wird in 5 Sekunden neu geladen ...';
        setTimeout(function(){{ location.reload(); }},5000);
      }}
    }})
    .catch(function(e){{
      st.style.background='#fee'; st.style.color='#c00';
      st.textContent='Verbindungsfehler: '+e.message;
    }});
}}
function systemAction(action, msg) {{
  if(!confirm(msg)) return;
  var st=document.getElementById('systemStatus');
  st.style.display='block'; st.style.background='#eef'; st.style.color='#006';
  st.textContent='Wird ausgefuehrt ...';
  fetch('/admin/system',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{action:action}})}})
    .then(function(r){{ return r.json(); }})
    .then(function(d){{
      if(d.error){{
        st.style.background='#fee'; st.style.color='#c00';
        st.textContent='Fehler: '+d.error;
      }} else {{
        st.style.background='#efe'; st.style.color='#060';
        st.textContent=d.message;
      }}
    }})
    .catch(function(e){{
      st.style.background='#fee'; st.style.color='#c00';
      st.textContent='Verbindungsfehler: '+e.message;
    }});
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

    upload_log_file = get_upload_log_path(config_file)
    title = cfg.get("web", "title", fallback="RPI Picture Show")
    greeting = cfg.get("web", "greeting", fallback="Willkommen! Laden Sie hier Ihre Bilder hoch.")

    app = Flask(__name__)
    app.secret_key = os.urandom(24)
    max_upload_mb = cfg.getint("web", "max_upload_mb", fallback=256)
    app.config["MAX_CONTENT_LENGTH"] = max_upload_mb * 1024 * 1024

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

    def build_upload_log_html() -> str:
        entries = load_upload_log(upload_log_file)
        if not entries:
            return '<div class="log-empty">Noch keine Uploads protokolliert.</div>'
        rows = []
        for e in reversed(entries):
            rows.append(
                f'<tr><td>{e.get("time","")}</td>'
                f'<td>{e.get("file","")}</td>'
                f'<td>{e.get("folder","")}</td>'
                f'<td>{e.get("ip","")}</td></tr>'
            )
        return (
            '<table class="log-table"><thead><tr>'
            '<th>Zeitpunkt</th><th>Datei</th><th>Ordner</th><th>IP-Adresse</th>'
            '</tr></thead><tbody>' + "".join(rows) + '</tbody></table>'
        )

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
            version=get_version(),
            max_upload_mb=max_upload_mb,
        )
        return Response(html, mimetype="text/html")

    @app.route("/upload", methods=["POST"])
    def upload():
        files = request.files.getlist("image")
        files = [f for f in files if f.filename]
        if not files:
            return redirect(url_for("index", msg="Keine Datei ausgewaehlt.", type="error"))
        if not check_free_space():
            return redirect(url_for("index", msg="Nicht genug Speicherplatz!", type="error"))
        saved = []
        skipped = []
        duplicates = []
        client_ip = request.remote_addr
        max_log = reload_cfg().getint("logging", "upload_log_max", fallback=UPLOAD_LOG_MAX_DEFAULT)
        for file in files:
            if not allowed_file(file.filename):
                skipped.append(file.filename)
                continue
            safe_name = secure_filename(file.filename)
            if file_exists_in_folder(folder_map["uploaded"], safe_name):
                duplicates.append(file.filename)
                continue
            filename = make_timestamped_name(safe_name)
            dest = os.path.join(folder_map["uploaded"], filename)
            file.save(dest)
            log.info("Upload: %s von IP %s", filename, client_ip)
            log_upload_entry(upload_log_file, filename, "uploaded", client_ip, max_log)
            saved.append(filename)
        if not saved and not duplicates and skipped:
            return redirect(url_for("index", msg="Nicht unterstuetztes Dateiformat.", type="error"))
        msg_parts = []
        if saved:
            msg_parts.append(f"{len(saved)} Bild(er) erfolgreich hochgeladen!")
        if duplicates:
            msg_parts.append(f"{len(duplicates)} bereits vorhanden.")
        if skipped:
            msg_parts.append(f"{len(skipped)} uebersprungen (Format).")
        return redirect(url_for("index", msg=" ".join(msg_parts), type="success" if saved else "error"))

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
            upload_log_html=build_upload_log_html(),
            upload_log_max=current_cfg.getint("logging", "upload_log_max", fallback=UPLOAD_LOG_MAX_DEFAULT),
            version=get_version(),
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
        # Upload log max
        log_max = request.form.get("upload_log_max", "")
        if log_max.isdigit() and int(log_max) >= 10:
            if not current_cfg.has_section("logging"):
                current_cfg.add_section("logging")
            current_cfg.set("logging", "upload_log_max", log_max)
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
        files = request.files.getlist("image")
        files = [f for f in files if f.filename]
        if not files:
            return redirect(url_for("admin_dashboard", msg="Keine Datei ausgewaehlt.", type="error"))
        if not check_free_space():
            return redirect(url_for("admin_dashboard", msg="Nicht genug Speicherplatz!", type="error"))
        saved = []
        skipped = []
        duplicates = []
        client_ip = request.remote_addr
        max_log = reload_cfg().getint("logging", "upload_log_max", fallback=UPLOAD_LOG_MAX_DEFAULT)
        for file in files:
            if not allowed_file(file.filename):
                skipped.append(file.filename)
                continue
            safe_name = secure_filename(file.filename)
            if file_exists_in_folder(folder_map[folder], safe_name):
                duplicates.append(file.filename)
                continue
            filename = make_timestamped_name(safe_name)
            dest = os.path.join(folder_map[folder], filename)
            file.save(dest)
            log.info("Admin-Upload: %s -> %s/ von IP %s", filename, folder, client_ip)
            log_upload_entry(upload_log_file, filename, folder, client_ip, max_log)
            saved.append(filename)
        # Trigger slideshow rescan
        try:
            with open(RESCAN_TRIGGER, "w") as f:
                f.write("rescan")
        except OSError:
            pass
        if not saved and not duplicates and skipped:
            return redirect(url_for("admin_dashboard", msg="Nicht unterstuetztes Dateiformat.", type="error"))
        msg_parts = []
        if saved:
            msg_parts.append(f"{len(saved)} Datei(en) hochgeladen in {folder}/.")
        if duplicates:
            msg_parts.append(f"{len(duplicates)} bereits vorhanden.")
        if skipped:
            msg_parts.append(f"{len(skipped)} uebersprungen (Format).")
        return redirect(url_for("admin_dashboard", msg=" ".join(msg_parts), type="success" if saved else "error"))

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
            if folder in ("logo", "pictures"):
                try:
                    with open(RESCAN_TRIGGER, "w") as f:
                        f.write("rescan")
                except OSError:
                    pass
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

    # ---------------------------------------------------------------
    # Update routes
    # ---------------------------------------------------------------

    @app.route("/admin/check-update")
    @require_admin
    def admin_check_update():
        app_dir = os.path.dirname(os.path.abspath(__file__))
        # Pruefen ob Git-Repository vorhanden ist
        if not os.path.isdir(os.path.join(app_dir, ".git")):
            return Response(
                json.dumps({"error": "Kein Git-Repository gefunden. Bitte mit 'git clone' installieren (siehe README)."}),
                mimetype="application/json",
            )
        try:
            proc = subprocess.run(
                ["git", "-C", app_dir, "fetch", "origin"],
                capture_output=True, text=True, timeout=30,
            )
            if proc.returncode != 0:
                return Response(
                    json.dumps({"error": "git fetch fehlgeschlagen: " + proc.stderr.strip()}),
                    mimetype="application/json",
                )
            proc = subprocess.run(
                ["git", "-C", app_dir, "show", "origin/master:VERSION"],
                capture_output=True, text=True, timeout=10,
            )
            if proc.returncode != 0:
                return Response(
                    json.dumps({"error": "Konnte Remote-Version nicht lesen."}),
                    mimetype="application/json",
                )
            remote_version = proc.stdout.strip()
            current_version = get_version()
            return Response(
                json.dumps({
                    "update_available": remote_version != current_version,
                    "current": current_version,
                    "remote": remote_version,
                }),
                mimetype="application/json",
            )
        except subprocess.TimeoutExpired:
            return Response(
                json.dumps({"error": "Zeitueberschreitung bei der Verbindung zu GitHub."}),
                mimetype="application/json",
            )
        except Exception as e:
            return Response(
                json.dumps({"error": str(e)}),
                mimetype="application/json",
            )

    @app.route("/admin/update", methods=["POST"])
    @require_admin
    def admin_do_update():
        app_dir = os.path.dirname(os.path.abspath(__file__))
        # Pruefen ob Git-Repository vorhanden ist
        if not os.path.isdir(os.path.join(app_dir, ".git")):
            return Response(
                json.dumps({"error": "Kein Git-Repository gefunden. Bitte mit 'git clone' installieren (siehe README)."}),
                mimetype="application/json",
            )
        try:
            # git pull (config.ini ist gitignored, kein Konflikt moeglich)
            proc = subprocess.run(
                ["git", "-C", app_dir, "pull", "origin", "master"],
                capture_output=True, text=True, timeout=60,
            )
            if proc.returncode != 0:
                return Response(
                    json.dumps({"error": "git pull fehlgeschlagen: " + proc.stderr.strip()}),
                    mimetype="application/json",
                )

            new_version = get_version()
            log.info("Update auf v%s durchgefuehrt", new_version)

            # Services nach kurzer Verzoegerung neu starten
            def restart_services():
                time.sleep(2)
                try:
                    subprocess.run(
                        ["sudo", "systemctl", "restart", "rpi-slideshow", "rpi-slideshow-web"],
                        timeout=30,
                    )
                except Exception:
                    log.error("Service-Neustart fehlgeschlagen")

            threading.Thread(target=restart_services, daemon=True).start()

            return Response(
                json.dumps({"new_version": new_version, "restarting": True}),
                mimetype="application/json",
            )
        except subprocess.TimeoutExpired:
            return Response(
                json.dumps({"error": "Zeitueberschreitung beim Update."}),
                mimetype="application/json",
            )
        except Exception as e:
            return Response(
                json.dumps({"error": str(e)}),
                mimetype="application/json",
            )

    # ---------------------------------------------------------------
    # System routes (shutdown, reboot, service control)
    # ---------------------------------------------------------------

    @app.route("/admin/system", methods=["POST"])
    @require_admin
    def admin_system():
        data = request.get_json(silent=True) or {}
        action = data.get("action", "")

        ALLOWED = {
            "stop-slideshow": {
                "cmd": ["sudo", "systemctl", "stop", "rpi-slideshow"],
                "msg": "Slideshow gestoppt. Konsole sollte wieder sichtbar sein.",
            },
            "start-slideshow": {
                "cmd": ["sudo", "systemctl", "start", "rpi-slideshow"],
                "msg": "Slideshow gestartet.",
            },
            "restart-slideshow": {
                "cmd": ["sudo", "systemctl", "restart", "rpi-slideshow"],
                "msg": "Slideshow neu gestartet.",
            },
            "reboot": {
                "cmd": ["sudo", "systemctl", "reboot"],
                "msg": "System wird neu gestartet ...",
                "delay": True,
            },
            "shutdown": {
                "cmd": ["sudo", "systemctl", "poweroff"],
                "msg": "System wird heruntergefahren ...",
                "delay": True,
            },
        }

        if action not in ALLOWED:
            return Response(
                json.dumps({"error": "Unbekannte Aktion: " + action}),
                mimetype="application/json",
            )

        spec = ALLOWED[action]
        log.info("System-Aktion: %s", action)

        if spec.get("delay"):
            # Delayed execution so the HTTP response can be sent first
            def delayed_exec():
                time.sleep(2)
                try:
                    subprocess.run(spec["cmd"], timeout=30)
                except Exception:
                    log.error("System-Aktion fehlgeschlagen: %s", action)
            threading.Thread(target=delayed_exec, daemon=True).start()
        else:
            try:
                proc = subprocess.run(
                    spec["cmd"], capture_output=True, text=True, timeout=30,
                )
                if proc.returncode != 0:
                    return Response(
                        json.dumps({"error": proc.stderr.strip() or "Befehl fehlgeschlagen"}),
                        mimetype="application/json",
                    )
            except subprocess.TimeoutExpired:
                return Response(
                    json.dumps({"error": "Zeitueberschreitung"}),
                    mimetype="application/json",
                )

        return Response(
            json.dumps({"message": spec["msg"]}),
            mimetype="application/json",
        )

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def ensure_ssl_cert(cert_path: str, key_path: str):
    """Erzeugt self-signed Zertifikat falls nicht vorhanden."""
    if os.path.isfile(cert_path) and os.path.isfile(key_path):
        return
    os.makedirs(os.path.dirname(cert_path), exist_ok=True)
    log.info("Erzeuge Self-signed SSL-Zertifikat ...")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", key_path, "-out", cert_path,
            "-days", "3650", "-nodes",
            "-subj", "/CN=rpi-picture-show",
        ],
        check=True,
        capture_output=True,
    )
    log.info("SSL-Zertifikat erzeugt: %s", cert_path)


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    cfg = load_config(config_path or get_config_path())
    use_https = cfg.getboolean("web", "https", fallback=False)
    port = cfg.getint("web", "port", fallback=443 if use_https else 8080)

    app = create_app(config_path)

    ssl_ctx = None
    if use_https:
        ssl_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ssl")
        cert = cfg.get("web", "ssl_cert", fallback=os.path.join(ssl_dir, "cert.pem"))
        key = cfg.get("web", "ssl_key", fallback=os.path.join(ssl_dir, "key.pem"))
        ensure_ssl_cert(cert, key)
        ssl_ctx = (cert, key)
        log.info("Starte Web-Upload auf Port %d (HTTPS) ...", port)
    else:
        log.info("Starte Web-Upload auf Port %d ...", port)

    app.run(host="0.0.0.0", port=port, debug=False, ssl_context=ssl_ctx)


if __name__ == "__main__":
    main()
