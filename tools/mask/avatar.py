"""Local geometric avatar generator (5x5 grid mirrored to 10x5).

MASK never fetches an avatar from a public service: reverse image
search defeats those instantly. Instead we generate a small, visually
distinct pattern deterministically from the alias handle, render it
to SVG (the canonical wire form), and rasterise to PNG via Pillow
for display and optional export.

Determinism matters for two reasons:

- Round-tripping: ``mask://`` carries only the SHA-256 of the SVG;
  the PNG is regenerable from the alias.
- Pentesting: ``avatar_deterministic`` asserts the SVG bytes are
  identical for the same seed.

The algorithm: hash the seed to 256 bits, use the first byte as a
hue, walk the remaining bytes bit-by-bit to fill a 5x5 grid, mirror
to 10x5. Two colours: the seeded hue and a near-black background.
The grid is mirrored horizontally so the result looks like a face,
not a barcode. This is the same technique GitHub's identicons use,
without the third-party dep.
"""
from __future__ import annotations

import colorsys
import hashlib
import io
import textwrap
from dataclasses import dataclass


SVG_VIEWBOX = 10        # 10 cells wide (5 mirrored), 10 cells tall (5x2 rows scaled)
GRID_SIDE = 5           # 5 columns drawn; mirrored to 10
GRID_ROWS = 10          # 10 rows drawn (full height; not mirrored vertically)
PNG_SIZE = 256          # default rasterised pixel size for the PNG export


@dataclass(frozen=True)
class Avatar:
    """A locally-rendered avatar bundle."""

    sha256: str          # hex digest of the canonical SVG bytes (wire form)
    svg: str             # canonical SVG bytes as a unicode string
    png_bytes: bytes     # 256x256 PNG, Pillow-rendered, deterministic for the seed


def _palette(seed: bytes) -> tuple[str, str]:
    """Pick foreground + background hex colours from the seed.

    Foreground: a high-saturation colour at a hue derived from the
    first seed byte. Background: dark grey, fixed (keeps the chrome
    palette honest and ensures the SVG looks the same against the
    terminal background regardless of seed).
    """
    h = seed[0] / 255.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.75, 0.92)
    fg = f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"
    bg = "#1a1a1a"
    return fg, bg


def _grid(seed: bytes) -> list[list[bool]]:
    """Walk seed bits to fill a 5xN grid (where N == GRID_ROWS).

    Mirrored horizontally to 10 wide so the result reads as a face.
    Uses bits from the seed deterministically: 5 * GRID_ROWS = 50
    bits, which fits in the first 7 bytes of the SHA-256 digest.
    The remaining bytes are unused; intentional, the grid is small.
    """
    needed_bits = GRID_SIDE * GRID_ROWS
    bits: list[bool] = []
    i = 0
    while len(bits) < needed_bits:
        byte = seed[i % len(seed)]
        for bit in range(8):
            bits.append(bool(byte & (1 << bit)))
            if len(bits) == needed_bits:
                break
        i += 1
    grid: list[list[bool]] = []
    idx = 0
    for _row in range(GRID_ROWS):
        row: list[bool] = []
        for _col in range(GRID_SIDE):
            row.append(bits[idx])
            idx += 1
        # Mirror to width 10. Centre column (the last of the 5) is
        # NOT duplicated -- mirror reflects the first 5 to the next 5
        # so the avatar looks like a face with a centre line of pixels.
        mirrored = row + list(reversed(row))
        grid.append(mirrored)
    return grid


def _render_svg(grid: list[list[bool]], fg: str, bg: str) -> str:
    """Render the grid as a canonical, whitespace-stable SVG string.

    The output is byte-deterministic: no random IDs, no timestamps,
    no comments. SHA-256 of this string is what ``mask://`` carries.
    """
    width = len(grid[0])
    height = len(grid)
    rects: list[str] = []
    for y, row in enumerate(grid):
        for x, on in enumerate(row):
            if on:
                rects.append(f'<rect x="{x}" y="{y}" width="1" height="1"/>')
    body = "".join(rects)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {width} {height}" '
        f'shape-rendering="crispEdges">'
        f'<rect width="{width}" height="{height}" fill="{bg}"/>'
        f'<g fill="{fg}">{body}</g>'
        f'</svg>'
    )


def _rasterise(grid: list[list[bool]], fg: str, bg: str, size: int) -> bytes:
    """Rasterise the grid to a PNG using Pillow.

    Pillow's default PNG settings are deterministic given pinned
    zlib parameters; two consecutive renders of the same seed
    produce byte-identical PNG output. We do NOT call Pillow's
    optimize=True because that path varies across Pillow versions.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError as e:    # pragma: no cover -- runtime dep
        raise RuntimeError(
            "Pillow is required for MASK avatar rendering. "
            "Install with: pip install Pillow>=10"
        ) from e

    width = len(grid[0])
    height = len(grid)
    cell = size // max(width, height)
    # Square image with the grid centred; aspect-correct.
    img_w = cell * width
    img_h = cell * height
    img = Image.new("RGB", (img_w, img_h), bg)
    draw = ImageDraw.Draw(img)
    for y, row in enumerate(grid):
        for x, on in enumerate(row):
            if on:
                draw.rectangle(
                    [(x * cell, y * cell),
                     ((x + 1) * cell - 1, (y + 1) * cell - 1)],
                    fill=fg,
                )
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=False, compress_level=6)
    return buf.getvalue()


def generate_avatar(seed: bytes, *, size: int = PNG_SIZE) -> Avatar:
    """Generate the avatar bundle for ``seed`` (typically alias-derived).

    Callers pass either the alias handle's UTF-8 bytes or a fresh
    32-byte random seed; either way, the SVG and PNG are deterministic
    functions of the bytes. ``size`` is the PNG width in pixels.
    """
    digest = hashlib.sha256(seed).digest()
    fg, bg = _palette(digest)
    grid = _grid(digest)
    svg = _render_svg(grid, fg, bg)
    svg_sha = hashlib.sha256(svg.encode("utf-8")).hexdigest()
    png = _rasterise(grid, fg, bg, size)
    return Avatar(sha256=svg_sha, svg=svg, png_bytes=png)


def block_preview(seed: bytes, *, rows: int = 8) -> str:
    """Render a compact text-block preview of the grid (for the TUI).

    Two characters per cell (Unicode block) so the aspect ratio
    matches the SVG when displayed in a typical terminal font.
    """
    digest = hashlib.sha256(seed).digest()
    grid = _grid(digest)
    lines: list[str] = []
    # Sample at most ``rows`` rows from the grid.
    step = max(1, len(grid) // rows)
    for row in grid[::step][:rows]:
        line = "".join("##" if cell else "  " for cell in row)
        lines.append(line)
    return "\n".join(lines)


__all__ = ["Avatar", "generate_avatar", "block_preview",
           "PNG_SIZE", "GRID_SIDE", "GRID_ROWS"]
