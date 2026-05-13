"""Pillow-drawn icon library for Support Notes email slots.

Two categories of icon are available:

Drawn icons — programmatically drawn at 4× (80×80) then downsampled with
LANCZOS. Only Pillow required; no external SVG library.

Bundled icons — the 7 brand PNG files in ``builder/assets/icons/``.
Icons that carry their own dark-circle backgrounds (video, expert-series,
support-kit) are resize-only.  Bare dark-on-light icons (kba, docs, download,
youtube) are colour-normalised to ``DEFAULT_COLOR`` via luminance inversion so
they render consistently in the email.

Usage
-----
>>> from builder import icon_library
>>> png_bytes = icon_library.render_png("kba", size=40)
>>> list(icon_library.available())
['arrow-right', 'bookmark', 'docs', 'document', 'download', ...]
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw

# ── Drawing constants ────────────────────────────────────────────────────────

_SCALE = 4          # draw at 4× then downscale for LANCZOS anti-aliasing
_BASE = 20 * _SCALE # canvas size: 80×80
_W = 5              # stroke width at 4× scale (≈1.25 px at 20 px display)
DEFAULT_COLOR = "#000028"   # Siemens dark navy — matches email body text

ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "icons"


# ── Low-level helpers ────────────────────────────────────────────────────────

def _canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGBA", (_BASE, _BASE), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _rgba(hex_color: str) -> tuple[int, int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255


def _export(img: Image.Image, size: int) -> bytes:
    out = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Icon draw functions (all operate on the 80×80 canvas) ───────────────────

def _document(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Page with folded top-right corner and three text lines."""
    fold = 18
    pts = [(10, 5), (62 - fold, 5), (62, 5 + fold), (62, 75), (10, 75)]
    # White fill so the fold stands out
    draw.polygon(pts, fill=(255, 255, 255, 180), outline=None)
    # Outline edges
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=c, width=w)
    draw.line([pts[-1], pts[0]], fill=c, width=w)
    # Fold crease
    draw.line([(62 - fold, 5), (62 - fold, 5 + fold)], fill=c, width=w)
    draw.line([(62 - fold, 5 + fold), (62, 5 + fold)], fill=c, width=w)
    # Text lines
    for ly in (40, 52, 63):
        draw.line([(20, ly), (54, ly)], fill=c, width=w)


def _tag(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Price tag (pentagon pointing right with a hole)."""
    pts = [(10, 12), (10, 68), (46, 68), (70, 40), (46, 12)]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=c, width=w)
    draw.line([pts[-1], pts[0]], fill=c, width=w)
    draw.ellipse([22, 34, 36, 46], outline=c, width=w)


def _envelope(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Mail envelope with V-shaped flap."""
    draw.rectangle([5, 18, 75, 62], outline=c, width=w)
    draw.line([(5, 18), (40, 44)], fill=c, width=w)
    draw.line([(40, 44), (75, 18)], fill=c, width=w)


def _download(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Down arrow dropping into a tray."""
    draw.line([(40, 6), (40, 54)], fill=c, width=w)
    draw.line([(22, 38), (40, 56)], fill=c, width=w)
    draw.line([(40, 56), (58, 38)], fill=c, width=w)
    draw.line([(14, 64), (66, 64)], fill=c, width=w)
    draw.line([(14, 64), (14, 74)], fill=c, width=w)
    draw.line([(66, 64), (66, 74)], fill=c, width=w)


def _bookmark(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Bookmark ribbon with V-notch at the bottom."""
    pts = [(18, 5), (62, 5), (62, 76), (40, 58), (18, 76)]
    for i in range(len(pts) - 1):
        draw.line([pts[i], pts[i + 1]], fill=c, width=w)
    draw.line([pts[-1], pts[0]], fill=c, width=w)


def _info(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Circle with information 'i'."""
    draw.ellipse([4, 4, 76, 76], outline=c, width=w)
    draw.ellipse([35, 17, 45, 27], fill=c)          # dot
    draw.line([(40, 33), (40, 61)], fill=c, width=w + 2)  # stem


def _arrow_right(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Right-pointing arrow."""
    draw.line([(8, 40), (62, 40)], fill=c, width=w)
    draw.line([(44, 22), (62, 40)], fill=c, width=w)
    draw.line([(44, 58), (62, 40)], fill=c, width=w)


def _magnifier(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Magnifying glass / search."""
    draw.ellipse([6, 6, 54, 54], outline=c, width=w)
    draw.line([(48, 48), (72, 72)], fill=c, width=w + 2)


def _link(draw: ImageDraw.ImageDraw, c: tuple, w: int) -> None:
    """Two interlocking arcs (chain link)."""
    # Left arc (open on right)
    draw.arc([6, 22, 54, 58], start=90, end=270, fill=c, width=w)
    draw.line([(30, 22), (44, 22)], fill=c, width=w)
    draw.line([(30, 58), (44, 58)], fill=c, width=w)
    # Right arc (open on left)
    draw.arc([26, 22, 74, 58], start=270, end=90, fill=c, width=w)
    draw.line([(36, 22), (50, 22)], fill=c, width=w)
    draw.line([(36, 58), (50, 58)], fill=c, width=w)


# ── Drawn-icon registry ───────────────────────────────────────────────────────

_ICONS: dict[str, tuple[str, Callable]] = {
    "document":    ("Document",    _document),
    "tag":         ("Tag",         _tag),
    "envelope":    ("Envelope",    _envelope),
    "download-drawn": ("Download (drawn)", _download),
    "bookmark":    ("Bookmark",    _bookmark),
    "info":        ("Info",        _info),
    "arrow-right": ("Arrow →",     _arrow_right),
    "magnifier":   ("Search",      _magnifier),
    "link":        ("Link",        _link),
}

# ── Bundled PNG registry ──────────────────────────────────────────────────────
# Each entry: label, filename, colorize
# colorize=True  → dark-on-light icon: normalise to DEFAULT_COLOR via
#                  luminance inversion (removes white/transparent backgrounds,
#                  unifies colour palette).
# colorize=False → icon has its own dark-circle background: resize only.

_BUNDLED: dict[str, tuple[str, str, bool]] = {
    "kba":           ("KBA Article",   "kba-icon.png",           True),
    "docs":          ("Docs",          "docs-icon.png",          True),
    "download":      ("Download",      "download-icon.png",      True),
    "youtube":       ("YouTube",       "youtube-icon.png",       True),
    "video":         ("Video",         "video-icon.png",         False),
    "expert-series": ("Expert Series", "expert-series-icon.png", False),
    "support-kit":   ("Support Kit",   "support-kit-icon.png",   False),
}


# ── Bundled PNG helpers ───────────────────────────────────────────────────────

def _square_pad(img: Image.Image) -> Image.Image:
    """Pad a non-square image to square with transparent borders."""
    w, h = img.size
    if w == h:
        return img
    size = max(w, h)
    padded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    padded.paste(img, ((size - w) // 2, (size - h) // 2))
    return padded


def _colorize(img: Image.Image, hex_color: str) -> Image.Image:
    """Normalise a dark-on-light icon to a single colour on a transparent background.

    Uses luminance inversion as the alpha channel: dark pixels become fully
    opaque in `hex_color`; white/near-white pixels become transparent.

    Composites on white before extracting luminance so that icons with
    transparent backgrounds don't get inverted to fully-opaque black (transparent
    pixels have RGB=(0,0,0), luminance=0, which naively inverts to alpha=255).
    """
    img = img.convert("RGBA")
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    # Composite on white so transparent areas become white before inverting.
    white = Image.new("RGBA", img.size, (255, 255, 255, 255))
    white.paste(img, mask=img.split()[3])
    gray = white.convert("L")
    alpha = gray.point(lambda x: 255 - x)   # dark → opaque, light → transparent
    result = Image.new("RGBA", img.size, (r, g, b, 0))
    result.putalpha(alpha)
    return result


def _render_bundled(icon_name: str, size: int) -> bytes:
    _, filename, colorize = _BUNDLED[icon_name]
    img = Image.open(ASSETS_DIR / filename)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    img = _square_pad(img)
    if colorize:
        img = _colorize(img, DEFAULT_COLOR)
    img = img.resize((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# ── Public API ────────────────────────────────────────────────────────────────

def available() -> list[str]:
    """Return sorted list of all icon names (drawn + bundled)."""
    return sorted(set(_ICONS) | set(_BUNDLED))


def label(icon_name: str) -> str:
    """Return human-readable label for an icon name."""
    if icon_name in _BUNDLED:
        return _BUNDLED[icon_name][0]
    return _ICONS[icon_name][0] if icon_name in _ICONS else icon_name


def render_png(icon_name: str, color: str = DEFAULT_COLOR, size: int = 40) -> bytes:
    """Render `icon_name` to PNG bytes at `size`×`size` pixels.

    Bundled icons are loaded from ``builder/assets/icons/`` and processed.
    Drawn icons are rendered via Pillow at 4× then downsampled (LANCZOS).
    `color` applies only to drawn icons; bundled icons use their own colour
    processing (see ``_BUNDLED`` registry).
    """
    if icon_name in _BUNDLED:
        return _render_bundled(icon_name, size)
    entry = _ICONS.get(icon_name)
    if entry is None:
        raise ValueError(
            f"Unknown icon {icon_name!r}. Available: {available()}"
        )
    img, draw = _canvas()
    entry[1](draw, _rgba(color), _W)
    return _export(img, size)
