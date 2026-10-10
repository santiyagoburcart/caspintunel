"""Subscription QR codes on a designed background (bot photo, site modal, downloads).

The QR itself is never touched: black modules on white with the full 4-module
quiet zone, drawn module-by-module at an integer pixel size, on a white rounded
card centred on the background. No logo, no text, no recolouring.

Backgrounds: the bundled brand JPEGs in `qr_backgrounds/` (re-created by its
`generate.py`), an admin-uploaded image (`SiteConfig.qr_background_custom`), or
"plain" = the bare QR as before. The active one is `SiteConfig.qr_background`.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFilter, ImageOps

BG_DIR = Path(__file__).resolve().parent / "qr_backgrounds"
SIZE = 1080
QUIET = 4                       # modules of white around the code (QR spec minimum)
PLAIN = "plain"
CUSTOM = "custom"
DEFAULT = "caspian-light"

# key → (fa, en, light?)  — order = order in the admin picker
BUILT_IN = {
    "caspian-light": ("کاسپین روشن", "Caspian light", True),
    "caspian-dark": ("کاسپین تیره", "Caspian dark", False),
    "ocean-waves": ("موج‌های آبی", "Ocean waves", False),
    "geometric-green": ("هندسی سبز", "Geometric green", False),
    "network": ("شبکهٔ شب", "Night network", False),
    "aurora": ("شفق", "Aurora", False),
}
CHOICES = (PLAIN, *BUILT_IN, CUSTOM)

# custom upload limits
MAX_UPLOAD = 5 * 1024 * 1024
MIN_SIDE, MAX_SIDE = 512, 8000
UPLOAD_FORMATS = {"JPEG", "PNG", "WEBP"}


@dataclass(frozen=True)
class Layout:
    """Where the code landed: modules of `box` px starting at (x, y), `n` per side
    (quiet zone included)."""
    x: int
    y: int
    box: int
    n: int


def matrix(data: str) -> list[list[bool]]:
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=QUIET, box_size=1)
    qr.add_data(data)
    qr.make(fit=True)
    return qr.get_matrix()


def _code_image(m: list[list[bool]], box: int) -> Image.Image:
    n = len(m)
    small = Image.new("1", (n, n), 1)
    small.putdata([0 if v else 1 for row in m for v in row])
    return small.resize((n * box, n * box), Image.NEAREST).convert("RGB")


@lru_cache(maxsize=16)
def _builtin(key: str) -> Image.Image:
    return Image.open(BG_DIR / f"{key}.jpg").convert("RGB")


def _cover(img: Image.Image, size: int) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), (size, size), Image.LANCZOS)


def background_image(key: str, custom_file=None, size: int = SIZE) -> Image.Image | None:
    """The background for `key`, or None for plain. Falls back to the default
    brand background when the custom file is missing or unreadable."""
    if key == PLAIN:
        return None
    if key == CUSTOM and custom_file:
        try:
            custom_file.open("rb")
            try:
                img = Image.open(io.BytesIO(custom_file.read()))
                img.load()
            finally:
                custom_file.close()
            return _cover(img, size)
        except Exception:  # noqa: BLE001 — a broken upload must not break QR delivery
            key = DEFAULT
    if key not in BUILT_IN:
        key = DEFAULT
    return _cover(_builtin(key), size)


def compose(data: str, bg: Image.Image | None, size: int = SIZE) -> tuple[Image.Image, Layout]:
    m = matrix(data)
    n = len(m)
    if bg is None:                                   # plain: the bare code, 10 px modules
        box = 10
        return _code_image(m, box), Layout(0, 0, box, n)
    box = max(3, int(size * 0.58) // n)
    side = n * box
    x = y = (size - side) // 2
    canvas = bg.copy()
    pad = max(box, size // 40)                       # white card margin around the quiet zone
    card = (x - pad, y - pad, x + side + pad, y + side + pad)
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((card[0], card[1] + size // 90, card[2], card[3] + size // 90),
                                             radius=size // 24, fill=(0, 0, 0, 90))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), shadow.filter(ImageFilter.GaussianBlur(size // 45)))
    ImageDraw.Draw(canvas).rounded_rectangle(card, radius=size // 24, fill=(255, 255, 255, 255))
    canvas = canvas.convert("RGB")
    canvas.paste(_code_image(m, box), (x, y))
    return canvas, Layout(x, y, box, n)


def to_png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def active_background(size: int = SIZE) -> Image.Image | None:
    from apps.settings_app.models import SiteConfig

    cfg = SiteConfig.load()
    return background_image(cfg.qr_background or DEFAULT, cfg.qr_background_custom, size)


def qr_card_png(data: str) -> bytes:
    """PNG of `data` as a QR on the active background — what customers get."""
    return to_png(compose(data, active_background())[0])


def validate_upload(f) -> None:
    """Raises ValueError with a short reason for an unusable background upload."""
    if f.size > MAX_UPLOAD:
        raise ValueError(f"file too large (max {MAX_UPLOAD // (1024 * 1024)} MB)")
    try:
        img = Image.open(f)
        fmt = img.format
        img.verify()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("not a readable image") from exc
    finally:
        f.seek(0)
    if fmt not in UPLOAD_FORMATS:
        raise ValueError("use a JPEG, PNG or WebP image")
    w, h = img.size
    if min(w, h) < MIN_SIDE or max(w, h) > MAX_SIDE:
        raise ValueError(f"image must be {MIN_SIDE}–{MAX_SIDE} px on each side")
