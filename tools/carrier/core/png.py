"""PNG cover handling -- Pillow-backed LSB on RGB / RGBA / L channels.

We deliberately operate on the raw channel-byte buffer (``Image.tobytes``)
so each bit goes into the LSB of exactly one channel byte, with a
deterministic row-major / channel-interleaved order. PNG re-save
preserves byte-perfect channels (it's lossless), so the round-trip
is exact.

Modes handled:

* ``L``    — 8-bit grayscale,  1 channel  per pixel
* ``RGB``  — 8-bit per channel, 3 channels per pixel
* ``RGBA`` — 8-bit per channel, 4 channels per pixel

Other modes (P palette, 16-bit, F float) are rejected up front:
LSB on non-8-bit channels changes much more than 1/256 of the
visible value.
"""
from __future__ import annotations

import io
from dataclasses import dataclass

from tools.carrier.capacity import (
    Capacity, from_channel_bits, png_channel_bits,
)


_SUPPORTED_MODES = {"L", "RGB", "RGBA"}
_MODE_CHANNELS = {"L": 1, "RGB": 3, "RGBA": 4}


@dataclass(slots=True)
class PngCover:
    width: int
    height: int
    mode: str            # "L" / "RGB" / "RGBA"
    n_channels: int
    pixels: bytearray    # row-major, channel-interleaved (length = w*h*c)


def _require_pillow():
    try:
        from PIL import Image  # noqa: F401
    except ImportError as e:  # pragma: no cover -- runtime dep
        raise RuntimeError(
            "CARRIER needs Pillow for PNG covers. "
            "Install with: pip install 'Pillow>=10'"
        ) from e


def open_cover(data: bytes) -> PngCover:
    """Open a PNG and return its raw channel-byte buffer."""
    _require_pillow()
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception as e:
        raise ValueError(f"not a readable PNG: {e}") from e

    if img.format != "PNG":
        raise ValueError(f"cover must be PNG, got {img.format}")
    if img.mode == "P":
        img = img.convert("RGB")
    if img.mode not in _SUPPORTED_MODES:
        raise ValueError(
            f"unsupported PNG mode {img.mode!r}; expected one of {sorted(_SUPPORTED_MODES)}"
        )

    pixels = bytearray(img.tobytes())
    return PngCover(
        width=img.width, height=img.height,
        mode=img.mode, n_channels=_MODE_CHANNELS[img.mode],
        pixels=pixels,
    )


def cover_capacity(cover: PngCover, safety_factor: float | None = None) -> Capacity:
    bits = png_channel_bits(cover.width, cover.height, cover.n_channels)
    if safety_factor is None:
        from tools.carrier.capacity import DEFAULT_SAFETY_FACTOR
        safety_factor = DEFAULT_SAFETY_FACTOR
    return from_channel_bits(bits, safety_factor=safety_factor)


def lsb_samples(cover: PngCover) -> bytes:
    """Return the bytes used for chi-square LSB analysis -- the channel buffer."""
    return bytes(cover.pixels)


def embed(cover: PngCover, payload: bytes) -> bytes:
    """Embed ``payload`` (bytes) into ``cover.pixels`` and return PNG bytes."""
    _require_pillow()
    from PIL import Image

    pixels = bytearray(cover.pixels)
    _write_bits(pixels, payload)

    out_img = Image.frombytes(cover.mode, (cover.width, cover.height),
                              bytes(pixels))
    buf = io.BytesIO()
    out_img.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def extract(cover: PngCover, n_bytes: int) -> bytes:
    """Read the first ``n_bytes`` bytes of payload from the LSB plane."""
    if n_bytes < 0:
        raise ValueError(f"n_bytes must be non-negative, got {n_bytes}")
    return _read_bits(cover.pixels, n_bytes)


# ---------------------------------------------------------------------------
# Bit-level write / read primitives.  Shared with WAV (different sample
# strides), but kept here so the PNG file stays self-contained.
# ---------------------------------------------------------------------------

def _write_bits(buf: bytearray, payload: bytes) -> None:
    """LSB-write ``payload`` bytes (MSB-first within each byte) into ``buf``."""
    needed = len(payload) * 8
    if needed > len(buf):
        raise ValueError(
            f"buffer too small: need {needed} bits, have {len(buf)} bytes"
        )
    bit_index = 0
    for byte in payload:
        for shift in range(7, -1, -1):
            bit = (byte >> shift) & 1
            buf[bit_index] = (buf[bit_index] & 0xfe) | bit
            bit_index += 1


def _read_bits(buf: bytes | bytearray, n_bytes: int) -> bytes:
    """LSB-read ``n_bytes`` bytes (MSB-first within each byte) from ``buf``."""
    bits_needed = n_bytes * 8
    if bits_needed > len(buf):
        raise ValueError(
            f"buffer too small: need {bits_needed} bits, have {len(buf)} bytes"
        )
    out = bytearray(n_bytes)
    for byte_idx in range(n_bytes):
        value = 0
        for shift in range(7, -1, -1):
            value = (value << 1) | (buf[byte_idx * 8 + (7 - shift)] & 1)
        out[byte_idx] = value
    return bytes(out)


__all__ = [
    "PngCover", "open_cover", "cover_capacity",
    "lsb_samples", "embed", "extract",
]
