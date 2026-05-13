"""Headshot compositor: turn an arbitrary source image into a 120×120 PNG
on Siemens petrol-green (#00C1B6) — the brand background used in shipped
Support Notes emails.

Pipeline
--------
1. Open the source image (JPEG, PNG with or without alpha, etc).
2. If it has an alpha channel, use it directly. If it doesn't (i.e. a
   solid-bg JPG), produce a soft alpha mask via a corner-flood-fill on
   "near-white" pixels — covers the most common case (white-background
   passport photos like ``Junyoung Bai.jpg``).
3. Best-fit crop the source so the head fills the frame: square-crop
   centred horizontally, biased toward the top vertically (so the head
   sits high — torso doesn't dominate).
4. Resize to 120×120 with high-quality resampling.
5. Composite onto a solid #00C1B6 RGB canvas.
6. Encode as PNG and return the bytes.

The output bytes are ready for ``sfmc_client.replace_image_bytes`` to
upload as a speaker headshot.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Tuple

from PIL import Image, ImageChops, ImageFilter


# Siemens "Petrol 500" — sampled from the rendered headshots in the
# April 2026 Tessent shipped email (image004/005/006/007.png).
BRAND_GREEN_RGB: Tuple[int, int, int] = (0, 0xC1, 0xB6)

# Final output dimensions matching the shipped emails.
OUTPUT_SIZE = 120

# How aggressively to treat near-white pixels as background when removing
# a JPG's white background. 30 is a sensible default; lower → only pure
# white treated as bg; higher → cream/very pale grey also treated as bg.
WHITE_BG_TOLERANCE = 30

# Vertical-bias factor when square-cropping a portrait. 0.0 = crop centred,
# 1.0 = crop from the very top. We want the head positioned slightly above
# centre so the torso doesn't dominate at small sizes; 0.15 looks right
# against the shipped reference images.
TOP_BIAS = 0.15


@dataclass
class CompositionResult:
    """Output of the compositor."""
    png_bytes: bytes
    width: int = OUTPUT_SIZE
    height: int = OUTPUT_SIZE


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def composite_headshot(source_bytes: bytes) -> CompositionResult:
    """Process a source image and return a 120×120 PNG on the brand-green
    background, encoded as bytes."""
    if not source_bytes:
        raise ValueError("source_bytes is empty")

    src = Image.open(io.BytesIO(source_bytes))
    src.load()  # force decoding so format/mode is final

    # Step 1-2: get RGBA — either from alpha channel or by removing white bg
    rgba = _to_rgba(src)

    # Step 3: best-fit square crop centred horizontally, biased toward the top
    cropped = _square_crop_with_top_bias(rgba)

    # Step 4: resize to 120×120
    sized = cropped.resize((OUTPUT_SIZE, OUTPUT_SIZE), Image.Resampling.LANCZOS)

    # Step 5: encode as RGBA PNG — preserve transparency as-is.
    # The petrol-green background is applied by the email template's table cell
    # background, not baked into the image.
    buf = io.BytesIO()
    sized.save(buf, format="PNG", optimize=True)
    return CompositionResult(png_bytes=buf.getvalue())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_rgba(img: Image.Image) -> Image.Image:
    """Return an RGBA copy of `img` with a sensible alpha channel.

    * Already-RGBA images: returned as-is (with alpha preserved).
    * Images with implicit transparency (P + transparency, LA, etc.):
      converted via PIL's normal RGBA conversion.
    * Plain RGB images (e.g. white-bg JPGs): given a soft alpha mask
      built from corner-sampled "near-white" pixels.
    """
    if img.mode == "RGBA":
        return img.copy()
    if img.mode in ("LA", "PA"):
        return img.convert("RGBA")
    if img.mode == "P" and "transparency" in img.info:
        return img.convert("RGBA")

    # Plain RGB-like image. Convert and synthesise an alpha mask.
    rgb = img.convert("RGB")
    alpha = _synthesise_alpha_from_white_bg(rgb)
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


def _synthesise_alpha_from_white_bg(rgb: Image.Image) -> Image.Image:
    """Generate an L-mode alpha mask for an RGB image that has a (near-)
    white background.

    Approach: sample the four corners; if they're all near-white, treat the
    image as a "subject on white" portrait and produce alpha = 0 for
    near-white pixels and alpha = 255 elsewhere. We avoid heavyweight
    background-removal libraries — this is a pragmatic fallback for the
    well-lit passport-style photos the requesters supply when they don't
    pre-process via removebg.
    """
    w, h = rgb.size
    corners = [
        rgb.getpixel((0, 0)),
        rgb.getpixel((w - 1, 0)),
        rgb.getpixel((0, h - 1)),
        rgb.getpixel((w - 1, h - 1)),
    ]
    if not all(_is_near_white(c) for c in corners):
        # Not a white-bg photo — return fully opaque mask so the source's
        # natural background ends up overwriting our brand canvas.
        # The user can re-upload a transparent PNG if that's wrong.
        return Image.new("L", rgb.size, 255)

    # Build mask: 0 where near-white, 255 elsewhere
    r, g, b = rgb.split()
    threshold = 255 - WHITE_BG_TOLERANCE
    # mask = NOT (r > thr AND g > thr AND b > thr)
    near_white = (
        r.point(lambda v: 255 if v >= threshold else 0)
        .convert("L")
    )
    near_white = ImageChops.multiply(
        near_white,
        g.point(lambda v: 255 if v >= threshold else 0).convert("L"),
    )
    near_white = ImageChops.multiply(
        near_white,
        b.point(lambda v: 255 if v >= threshold else 0).convert("L"),
    )
    # Invert: bg=0, fg=255
    mask = ImageChops.invert(near_white)
    # Smooth the edge slightly so we don't get pixel-staircase artefacts on
    # the green background.
    mask = mask.filter(ImageFilter.GaussianBlur(radius=0.7))
    return mask


def _is_near_white(rgb: Tuple[int, int, int]) -> bool:
    threshold = 255 - WHITE_BG_TOLERANCE
    return all(v >= threshold for v in rgb[:3])


def _square_crop_with_top_bias(img: Image.Image) -> Image.Image:
    """Crop `img` to a square with a vertical bias toward the top.

    Best-fit means we use the smaller of width/height as the side length,
    then centre horizontally and bias upward vertically by `TOP_BIAS` of
    the available headroom.
    """
    w, h = img.size
    if w == h:
        return img
    side = min(w, h)
    if w >= h:
        # Landscape — crop horizontally centred
        x = (w - side) // 2
        y = 0
    else:
        # Portrait — bias toward top
        x = 0
        max_offset = h - side
        y = int(max_offset * TOP_BIAS)
    return img.crop((x, y, x + side, y + side))
