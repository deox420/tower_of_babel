"""Per-format channel-bit capacity + safe-margin calculator.

CARRIER touches one bit per channel/sample. The total bit budget
is straightforward, but using all of it leaves a chi-square trail.
The safe-capacity threshold is the fraction of channel bits we are
willing to flip before the cover starts looking tampered.

Below 1/8 of channel bits touched, the chi-square statistic
typically stays inside the null distribution; we use 0.125 as the
default safety factor, configurable per call.
"""
from __future__ import annotations

from dataclasses import dataclass


DEFAULT_SAFETY_FACTOR = 0.125


@dataclass(slots=True)
class Capacity:
    channel_bits: int       # total LSBs available on the cover
    safe_bits: int          # safe_bits = floor(channel_bits * factor)
    safe_bytes: int         # safe_bits // 8
    safety_factor: float


def from_channel_bits(channel_bits: int,
                      safety_factor: float = DEFAULT_SAFETY_FACTOR) -> Capacity:
    if channel_bits <= 0:
        raise ValueError("channel_bits must be positive")
    if not 0 < safety_factor <= 1:
        raise ValueError("safety_factor must be in (0, 1]")
    safe_bits = int(channel_bits * safety_factor)
    return Capacity(
        channel_bits=channel_bits,
        safe_bits=safe_bits,
        safe_bytes=safe_bits // 8,
        safety_factor=safety_factor,
    )


def png_channel_bits(width: int, height: int, n_channels: int) -> int:
    if min(width, height) <= 0 or n_channels not in (1, 3, 4):
        raise ValueError(f"unsupported PNG geometry: {width}x{height}x{n_channels}")
    return width * height * n_channels


def wav_channel_bits(n_frames: int, n_channels: int) -> int:
    if n_frames <= 0 or n_channels <= 0:
        raise ValueError("non-positive frame or channel count")
    return n_frames * n_channels


class PayloadTooLargeError(ValueError):
    """Raised when a framed payload exceeds the cover's safe capacity."""

    def __init__(self, needed: int, capacity: Capacity) -> None:
        super().__init__(
            f"payload needs {needed} bytes but cover safe-capacity is "
            f"{capacity.safe_bytes} bytes "
            f"(safety factor {capacity.safety_factor:.3f}; "
            f"channel bits {capacity.channel_bits})"
        )
        self.needed = needed
        self.capacity = capacity


__all__ = [
    "Capacity", "DEFAULT_SAFETY_FACTOR",
    "from_channel_bits", "png_channel_bits", "wav_channel_bits",
    "PayloadTooLargeError",
]
