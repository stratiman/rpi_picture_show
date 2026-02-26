#!/usr/bin/env python3
"""
RPI Picture Show - Fullscreen slideshow for Raspberry Pi Zero W.
Alternates between images from two folders (logo and pictures).
Uploaded images have priority over pictures and are moved to trash after display.
Runs without desktop environment using the framebuffer.
"""

import configparser
import logging
import mmap
import os
import random
import shutil
import signal
import sys
import time

import pygame

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("slideshow")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_config(path: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read(path)
    return cfg


def get_config_path() -> str:
    """Return the path to config.ini next to this script."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")


def get_version() -> str:
    version_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "VERSION")
    try:
        with open(version_file) as f:
            return f.read().strip()
    except OSError:
        return "?"

# ---------------------------------------------------------------------------
# Image collection
# ---------------------------------------------------------------------------

def collect_images(folder: str, recursive: bool = True) -> list[str]:
    """Collect all supported image files from *folder* (optionally recursive)."""
    images: list[str] = []
    if not os.path.isdir(folder):
        log.warning("Ordner existiert nicht: %s", folder)
        return images
    if recursive:
        for root, _dirs, files in os.walk(folder):
            for f in sorted(files):
                if f.lower().endswith(SUPPORTED_EXTENSIONS):
                    images.append(os.path.join(root, f))
    else:
        for f in sorted(os.listdir(folder)):
            full = os.path.join(folder, f)
            if os.path.isfile(full) and f.lower().endswith(SUPPORTED_EXTENSIONS):
                images.append(full)
    return images

# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def setup_fb_mirror(screen_w: int, screen_h: int):
    """Open /dev/fb0 and monkey-patch pygame.display.flip to mirror frames.

    SDL 2.28+ removed the fbcon driver, and kmsdrm on Pi 3 with Trixie
    does not render to the HDMI output.  As a workaround we let kmsdrm
    handle the pygame display surface (off-screen) and copy every frame
    to /dev/fb0 via mmap so it actually appears on the physical screen.
    """
    try:
        with open("/sys/class/graphics/fb0/bits_per_pixel") as f:
            bpp = int(f.read().strip())
        with open("/sys/class/graphics/fb0/stride") as f:
            stride = int(f.read().strip())
        with open("/sys/class/graphics/fb0/virtual_size") as f:
            fb_w, fb_h = map(int, f.read().strip().split(","))

        fb_file = open("/dev/fb0", "r+b")
        fbmap = mmap.mmap(fb_file.fileno(), stride * fb_h)

        # Pre-create a conversion surface matching the framebuffer depth
        conv = pygame.Surface((fb_w, fb_h), depth=bpp)

        _original_flip = pygame.display.flip

        def fb_flip():
            _original_flip()
            screen = pygame.display.get_surface()
            if screen is None:
                return
            conv.blit(screen, (0, 0))
            fbmap.seek(0)
            fbmap.write(conv.get_buffer().raw)

        pygame.display.flip = fb_flip
        log.info("Framebuffer-Mirror aktiv: /dev/fb0 (%dx%d, %dbpp)", fb_w, fb_h, bpp)
    except Exception as exc:
        log.debug("Framebuffer-Mirror nicht verfuegbar: %s", exc)


def init_display() -> pygame.Surface:
    """Initialise pygame display and set up framebuffer mirror if needed.

    On Pi with Trixie (SDL 2.28+), the fbcon driver is removed and kmsdrm
    creates a DRM plane that covers /dev/fb0.  We use the 'dummy' driver
    for off-screen rendering and mirror every frame to /dev/fb0 directly.
    """
    os.environ.setdefault("SDL_NOMOUSE", "1")

    # Read framebuffer resolution to use as screen size
    fb_w, fb_h = 1920, 1080  # safe default
    try:
        with open("/sys/class/graphics/fb0/virtual_size") as f:
            fb_w, fb_h = map(int, f.read().strip().split(","))
    except OSError:
        pass

    # Use dummy driver if /dev/fb0 exists (avoids kmsdrm covering the fb)
    has_fb = os.path.exists("/dev/fb0")
    if has_fb:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        pygame.display.init()
        log.info("Video-Treiber: dummy (Ausgabe ueber /dev/fb0)")
    else:
        # No framebuffer: try real display drivers (X11, Wayland, kmsdrm)
        drivers = ["kmsdrm", "directfb", "svgalib"]
        display_initialized = False
        for driver in drivers:
            os.environ["SDL_VIDEODRIVER"] = driver
            try:
                pygame.display.init()
                display_initialized = True
                log.info("Video-Treiber: %s", driver)
                break
            except pygame.error as e:
                log.debug("Treiber %s fehlgeschlagen: %s", driver, e)
                continue
        if not display_initialized:
            os.environ.pop("SDL_VIDEODRIVER", None)
            pygame.display.init()
            log.info("Video-Treiber: SDL default")

    pygame.font.init()

    screen = pygame.display.set_mode((fb_w, fb_h))
    log.info("Aufloesung: %dx%d", fb_w, fb_h)

    # Mirror every pygame.display.flip() to /dev/fb0
    if has_fb:
        setup_fb_mirror(fb_w, fb_h)

    return screen


def load_and_scale(path: str, screen_w: int, screen_h: int) -> pygame.Surface | None:
    """Load an image, scale it to fit the screen while keeping aspect ratio."""
    try:
        img = pygame.image.load(path).convert()
    except (pygame.error, FileNotFoundError, OSError) as exc:
        log.warning("Bild konnte nicht geladen werden: %s (%s)", path, exc)
        return None

    img_w, img_h = img.get_size()
    scale = min(screen_w / img_w, screen_h / img_h)
    new_w = int(img_w * scale)
    new_h = int(img_h * scale)
    return pygame.transform.smoothscale(img, (new_w, new_h))


def blit_centered(screen: pygame.Surface, img: pygame.Surface, bg_color: tuple[int, int, int]):
    """Draw *img* centered on *screen* with *bg_color* background."""
    screen.fill(bg_color)
    sw, sh = screen.get_size()
    iw, ih = img.get_size()
    x = (sw - iw) // 2
    y = (sh - ih) // 2
    screen.blit(img, (x, y))

# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------

def transition_none(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], _duration_ms: int):
    blit_centered(screen, new_img, bg_color)
    pygame.display.flip()


def transition_fade(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int):
    sw, sh = screen.get_size()
    old_surface = screen.copy()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    steps = max(1, duration_ms // 16)  # ~60 fps
    clock = pygame.time.Clock()

    for i in range(1, steps + 1):
        alpha = int(255 * i / steps)
        screen.blit(old_surface, (0, 0))
        new_surface.set_alpha(alpha)
        screen.blit(new_surface, (0, 0))
        pygame.display.flip()
        clock.tick(60)


def transition_slide(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int, direction: str = "left"):
    sw, sh = screen.get_size()
    old_surface = screen.copy()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    steps = max(1, duration_ms // 16)
    clock = pygame.time.Clock()

    for i in range(1, steps + 1):
        progress = i / steps
        offset = int(sw * progress)

        if direction == "left":
            screen.blit(old_surface, (-offset, 0))
            screen.blit(new_surface, (sw - offset, 0))
        else:
            screen.blit(old_surface, (offset, 0))
            screen.blit(new_surface, (-sw + offset, 0))

        pygame.display.flip()
        clock.tick(60)


def transition_slide_vertical(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int, direction: str = "up"):
    sw, sh = screen.get_size()
    old_surface = screen.copy()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    steps = max(1, duration_ms // 16)
    clock = pygame.time.Clock()

    for i in range(1, steps + 1):
        progress = i / steps
        offset = int(sh * progress)

        if direction == "up":
            screen.blit(old_surface, (0, -offset))
            screen.blit(new_surface, (0, sh - offset))
        else:
            screen.blit(old_surface, (0, offset))
            screen.blit(new_surface, (0, -sh + offset))

        pygame.display.flip()
        clock.tick(60)


def transition_zoom_in(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int):
    """New image grows from center to full size."""
    sw, sh = screen.get_size()
    old_surface = screen.copy()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    steps = max(1, duration_ms // 16)
    clock = pygame.time.Clock()

    for i in range(1, steps + 1):
        progress = i / steps
        # Ease-out curve for smoother feel
        progress = 1 - (1 - progress) ** 2
        w = max(1, int(sw * progress))
        h = max(1, int(sh * progress))
        scaled = pygame.transform.smoothscale(new_surface, (w, h))
        screen.blit(old_surface, (0, 0))
        screen.blit(scaled, ((sw - w) // 2, (sh - h) // 2))
        pygame.display.flip()
        clock.tick(60)


def transition_zoom_out(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int):
    """Old image shrinks to center, revealing new image."""
    sw, sh = screen.get_size()
    old_surface = screen.copy()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    steps = max(1, duration_ms // 16)
    clock = pygame.time.Clock()

    for i in range(1, steps + 1):
        progress = i / steps
        progress = progress ** 2  # ease-in
        remaining = 1 - progress
        w = max(1, int(sw * remaining))
        h = max(1, int(sh * remaining))
        scaled = pygame.transform.smoothscale(old_surface, (w, h))
        screen.blit(new_surface, (0, 0))
        screen.blit(scaled, ((sw - w) // 2, (sh - h) // 2))
        pygame.display.flip()
        clock.tick(60)


def transition_wipe(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int, direction: str = "left"):
    """New image is revealed by a wipe (old image stays, new overlays progressively)."""
    sw, sh = screen.get_size()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    steps = max(1, duration_ms // 16)
    clock = pygame.time.Clock()

    for i in range(1, steps + 1):
        progress = i / steps
        if direction == "left":
            w = int(sw * progress)
            screen.blit(new_surface, (0, 0), (0, 0, w, sh))
        elif direction == "right":
            w = int(sw * progress)
            x = sw - w
            screen.blit(new_surface, (x, 0), (x, 0, w, sh))
        elif direction == "down":
            h = int(sh * progress)
            screen.blit(new_surface, (0, 0), (0, 0, sw, h))
        else:  # up
            h = int(sh * progress)
            y = sh - h
            screen.blit(new_surface, (0, y), (0, y, sw, h))

        pygame.display.flip()
        clock.tick(60)


def transition_dissolve(screen: pygame.Surface, new_img: pygame.Surface, bg_color: tuple[int, int, int], duration_ms: int):
    """Pixelated dissolve - reveals new image in random blocks."""
    sw, sh = screen.get_size()

    new_surface = pygame.Surface((sw, sh))
    new_surface.fill(bg_color)
    iw, ih = new_img.get_size()
    new_surface.blit(new_img, ((sw - iw) // 2, (sh - ih) // 2))

    block_size = 16
    cols = (sw + block_size - 1) // block_size
    rows = (sh + block_size - 1) // block_size
    blocks = [(c, r) for r in range(rows) for c in range(cols)]
    random.shuffle(blocks)

    steps = max(1, duration_ms // 16)
    blocks_per_step = max(1, len(blocks) // steps)
    clock = pygame.time.Clock()

    idx = 0
    while idx < len(blocks):
        batch_end = min(idx + blocks_per_step, len(blocks))
        for c, r in blocks[idx:batch_end]:
            x = c * block_size
            y = r * block_size
            w = min(block_size, sw - x)
            h = min(block_size, sh - y)
            screen.blit(new_surface, (x, y), (x, y, w, h))
        idx = batch_end
        pygame.display.flip()
        clock.tick(60)


# All available transitions (excluding "random" which is handled separately)
TRANSITIONS = {
    "none": transition_none,
    "fade": transition_fade,
    "slide_left": lambda scr, img, bg, dur: transition_slide(scr, img, bg, dur, "left"),
    "slide_right": lambda scr, img, bg, dur: transition_slide(scr, img, bg, dur, "right"),
    "slide_up": lambda scr, img, bg, dur: transition_slide_vertical(scr, img, bg, dur, "up"),
    "slide_down": lambda scr, img, bg, dur: transition_slide_vertical(scr, img, bg, dur, "down"),
    "zoom_in": transition_zoom_in,
    "zoom_out": transition_zoom_out,
    "wipe_left": lambda scr, img, bg, dur: transition_wipe(scr, img, bg, dur, "left"),
    "wipe_right": lambda scr, img, bg, dur: transition_wipe(scr, img, bg, dur, "right"),
    "wipe_down": lambda scr, img, bg, dur: transition_wipe(scr, img, bg, dur, "down"),
    "wipe_up": lambda scr, img, bg, dur: transition_wipe(scr, img, bg, dur, "up"),
    "dissolve": transition_dissolve,
}

# Transitions eligible for random selection (all except "none")
_RANDOM_POOL = [fn for name, fn in TRANSITIONS.items() if name != "none"]

# ---------------------------------------------------------------------------
# Hex color helper
# ---------------------------------------------------------------------------

def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

class Slideshow:
    def __init__(self, config_path: str | None = None):
        self.running = True
        self.cfg = load_config(config_path or get_config_path())

        # Paths
        base = self.cfg.get("paths", "base_path", fallback="/home/pi/slideshow")
        logo_name = self.cfg.get("paths", "logo_folder", fallback="logo")
        pics_name = self.cfg.get("paths", "pictures_folder", fallback="pictures")
        uploaded_name = self.cfg.get("paths", "uploaded_folder", fallback="uploaded")
        trash_name = self.cfg.get("paths", "trash_folder", fallback="trash")
        self.logo_dir = os.path.join(base, logo_name)
        self.pics_dir = os.path.join(base, pics_name)
        self.uploaded_dir = os.path.join(base, uploaded_name)
        self.trash_dir = os.path.join(base, trash_name)

        # Ensure uploaded and trash directories exist
        os.makedirs(self.uploaded_dir, exist_ok=True)
        os.makedirs(self.trash_dir, exist_ok=True)

        # Timing
        self.logo_seconds = self.cfg.getfloat("timing", "logo_display_seconds", fallback=5.0)
        self.pics_seconds = self.cfg.getfloat("timing", "pictures_display_seconds", fallback=10.0)
        self.uploaded_seconds = self.cfg.getfloat("timing", "uploaded_display_seconds", fallback=8.0)

        # Display
        self.transition_name = self.cfg.get("display", "transition", fallback="fade")
        self.transition_duration_min = self.cfg.getint("display", "transition_duration_min_ms", fallback=300)
        self.transition_duration_max = self.cfg.getint("display", "transition_duration_max_ms", fallback=800)
        self.transition_duration_random = self.cfg.getboolean("display", "transition_duration_random", fallback=False)
        # Backwards compatibility: fall back to old single value if new keys missing
        if not self.cfg.has_option("display", "transition_duration_min_ms") and self.cfg.has_option("display", "transition_duration_ms"):
            val = self.cfg.getint("display", "transition_duration_ms", fallback=500)
            self.transition_duration_min = val
            self.transition_duration_max = val
        self.bg_color = hex_to_rgb(self.cfg.get("display", "background_color", fallback="#000000"))

        # Slideshow
        self.do_shuffle = self.cfg.getboolean("slideshow", "shuffle", fallback=False)
        self.recursive = self.cfg.getboolean("slideshow", "recursive", fallback=True)

        # Trash
        self.trash_days = self.cfg.getint("trash", "delete_after_days", fallback=30)

        # Transition function
        self.use_random_transition = self.transition_name == "random"
        if self.use_random_transition:
            self.transition_fn = None  # picked per image
        else:
            self.transition_fn = TRANSITIONS.get(self.transition_name, transition_fade)

    # ------------------------------------------------------------------

    def collect(self) -> tuple[list[str], list[str]]:
        logos = collect_images(self.logo_dir, self.recursive)
        pics = collect_images(self.pics_dir, self.recursive)
        log.info("Logos gefunden: %d  |  Bilder gefunden: %d", len(logos), len(pics))
        if self.do_shuffle:
            random.shuffle(logos)
            random.shuffle(pics)
        return logos, pics

    def get_uploaded_images(self) -> list[str]:
        """Collect images from the uploaded folder (always fresh, non-recursive)."""
        return collect_images(self.uploaded_dir, recursive=False)

    # ------------------------------------------------------------------

    def move_to_trash(self, path: str):
        """Move a displayed uploaded image to the trash folder."""
        filename = os.path.basename(path)
        # Add timestamp prefix to avoid name collisions
        trash_name = f"{int(time.time())}_{filename}"
        dest = os.path.join(self.trash_dir, trash_name)
        try:
            shutil.move(path, dest)
            log.info("In Papierkorb verschoben: %s -> %s", filename, trash_name)
        except OSError as exc:
            log.warning("Konnte Bild nicht in Papierkorb verschieben: %s (%s)", path, exc)

    def cleanup_trash(self):
        """Delete files in trash older than configured days."""
        if self.trash_days <= 0:
            return
        now = time.time()
        max_age = self.trash_days * 86400
        if not os.path.isdir(self.trash_dir):
            return
        for f in os.listdir(self.trash_dir):
            full = os.path.join(self.trash_dir, f)
            if not os.path.isfile(full):
                continue
            age = now - os.path.getmtime(full)
            if age > max_age:
                try:
                    os.remove(full)
                    log.info("Papierkorb: Geloescht (%.0f Tage alt): %s", age / 86400, f)
                except OSError as exc:
                    log.warning("Papierkorb: Konnte nicht loeschen: %s (%s)", f, exc)

    # ------------------------------------------------------------------

    def handle_events(self) -> bool:
        """Process pygame events. Return False to quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_q):
                return False
        return True

    # ------------------------------------------------------------------

    def show_image(self, screen: pygame.Surface, path: str, duration: float):
        """Load, transition to, and display *path* for *duration* seconds."""
        sw, sh = screen.get_size()
        img = load_and_scale(path, sw, sh)
        if img is None:
            return

        log.info("Zeige: %s (%.1fs)", os.path.basename(path), duration)
        if self.use_random_transition:
            fn = random.choice(_RANDOM_POOL)
        else:
            fn = self.transition_fn
        if self.transition_duration_random:
            dur = random.randint(self.transition_duration_min, self.transition_duration_max)
        else:
            dur = self.transition_duration_min
        fn(screen, img, self.bg_color, dur)

        # Wait for the display duration while checking events
        end_time = time.time() + duration
        while time.time() < end_time and self.running:
            if not self.handle_events():
                self.running = False
                return
            pygame.time.wait(100)

    # ------------------------------------------------------------------

    def run(self):
        log.info("RPI Picture Show v%s", get_version())
        signal.signal(signal.SIGTERM, lambda *_: setattr(self, "running", False))
        signal.signal(signal.SIGINT, lambda *_: setattr(self, "running", False))

        screen = init_display()

        while self.running:
            logos, pics = self.collect()
            self.cleanup_trash()

            if not logos and not pics:
                # Check if there are uploaded images even without logos/pics
                uploaded = self.get_uploaded_images()
                if not uploaded:
                    log.error("Keine Bilder gefunden! Warte 10 Sekunden ...")
                    screen.fill(self.bg_color)
                    pygame.display.flip()
                    time.sleep(10)
                    continue

            logo_idx = 0
            pics_idx = 0

            while self.running:
                # Show logo
                if logos:
                    self.show_image(screen, logos[logo_idx], self.logo_seconds)
                    logo_idx += 1
                    if logo_idx >= len(logos):
                        logo_idx = 0
                        break  # Re-scan folders

                if not self.running:
                    break

                # Picture slot: uploaded images have priority
                uploaded = self.get_uploaded_images()
                if uploaded:
                    # Show uploaded image and move to trash afterwards
                    upload_path = uploaded[0]
                    self.show_image(screen, upload_path, self.uploaded_seconds)
                    self.move_to_trash(upload_path)
                elif pics:
                    self.show_image(screen, pics[pics_idx], self.pics_seconds)
                    pics_idx += 1
                    if pics_idx >= len(pics):
                        pics_idx = 0
                        break  # Re-scan folders

        pygame.quit()
        log.info("Slideshow beendet.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    show = Slideshow(config_path)
    show.run()


if __name__ == "__main__":
    main()
