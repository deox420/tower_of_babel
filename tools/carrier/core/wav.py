"""WAV cover handling -- stdlib ``wave``, LSB on the low byte of each sample.

For every PCM sample (regardless of bit depth) the lowest byte
holds the LSB we modify. On 16-bit little-endian PCM that's
sample[0]; on 24/32-bit, still sample[0]. The other bytes of the
sample are passed through untouched.

The ``wave`` module handles RIFF framing for us; we round-trip
through ``readframes`` / ``writeframes`` keeping all parameters
(channels, sample width, frame rate, compression type) identical.
"""
from __future__ import annotations

import io
import wave
from dataclasses import dataclass

from tools.carrier.capacity import (
    Capacity, from_channel_bits, wav_channel_bits,
)


@dataclass(slots=True)
class WavCover:
    n_channels: int
    sample_width: int    # bytes per sample (1, 2, 3, or 4)
    frame_rate: int
    n_frames: int
    raw_frames: bytearray   # length = n_frames * n_channels * sample_width


def open_cover(data: bytes) -> WavCover:
    try:
        with wave.open(io.BytesIO(data), "rb") as r:
            params = r.getparams()
            frames = r.readframes(params.nframes)
    except wave.Error as e:
        raise ValueError(f"not a readable WAV: {e}") from e
    if params.comptype != "NONE":
        raise ValueError(f"WAV must be uncompressed PCM, got compression {params.comptype}")
    if params.sampwidth not in (1, 2, 3, 4):
        raise ValueError(f"unsupported sample width {params.sampwidth} bytes")
    return WavCover(
        n_channels=params.nchannels,
        sample_width=params.sampwidth,
        frame_rate=params.framerate,
        n_frames=params.nframes,
        raw_frames=bytearray(frames),
    )


def cover_capacity(cover: WavCover, safety_factor: float | None = None) -> Capacity:
    bits = wav_channel_bits(cover.n_frames, cover.n_channels)
    if safety_factor is None:
        from tools.carrier.capacity import DEFAULT_SAFETY_FACTOR
        safety_factor = DEFAULT_SAFETY_FACTOR
    return from_channel_bits(bits, safety_factor=safety_factor)


def lsb_samples(cover: WavCover) -> bytes:
    """Return only the LSB-bearing low bytes of each sample, for chi-square."""
    stride = cover.sample_width
    return bytes(cover.raw_frames[::stride])


def embed(cover: WavCover, payload: bytes) -> bytes:
    """Embed ``payload`` into the LSB of each sample's low byte; return WAV bytes."""
    frames = bytearray(cover.raw_frames)
    _write_bits_strided(frames, payload, stride=cover.sample_width)

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(cover.n_channels)
        w.setsampwidth(cover.sample_width)
        w.setframerate(cover.frame_rate)
        w.setnframes(cover.n_frames)
        w.writeframesraw(bytes(frames))
    return buf.getvalue()


def extract(cover: WavCover, n_bytes: int) -> bytes:
    if n_bytes < 0:
        raise ValueError(f"n_bytes must be non-negative, got {n_bytes}")
    return _read_bits_strided(cover.raw_frames, n_bytes, stride=cover.sample_width)


def _write_bits_strided(buf: bytearray, payload: bytes, *, stride: int) -> None:
    """LSB-write each bit into ``buf[i * stride]``."""
    needed = len(payload) * 8
    capacity_bytes = len(buf) // stride
    if needed > capacity_bytes:
        raise ValueError(
            f"WAV buffer too small: need {needed} LSB slots, have {capacity_bytes}"
        )
    bit_index = 0
    for byte in payload:
        for shift in range(7, -1, -1):
            bit = (byte >> shift) & 1
            off = bit_index * stride
            buf[off] = (buf[off] & 0xfe) | bit
            bit_index += 1


def _read_bits_strided(buf: bytes | bytearray, n_bytes: int, *, stride: int) -> bytes:
    capacity_bytes = len(buf) // stride
    if n_bytes * 8 > capacity_bytes:
        raise ValueError(
            f"WAV buffer too small: need {n_bytes * 8} LSB slots, have {capacity_bytes}"
        )
    out = bytearray(n_bytes)
    for byte_idx in range(n_bytes):
        value = 0
        for shift in range(7, -1, -1):
            slot = (byte_idx * 8 + (7 - shift)) * stride
            value = (value << 1) | (buf[slot] & 1)
        out[byte_idx] = value
    return bytes(out)


__all__ = [
    "WavCover", "open_cover", "cover_capacity",
    "lsb_samples", "embed", "extract",
]
