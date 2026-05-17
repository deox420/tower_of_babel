"""CARRIER end-to-end embed / extract pipeline.

Brings together: ``shared.crypto.kdf.argon2id`` (passphrase ->
AES-256 key), ``shared.crypto.aead.encrypt`` (AES-256-GCM), the
header packer in ``tools.carrier.header``, the chi-square sanity
check in ``tools.carrier.chisquare``, and the per-format LSB
embedders in ``tools.carrier.core``.

Two public entry points:

* ``embed_payload(cover_bytes, payload_bytes, passphrase, format, ...)
  -> EmbedReport``
* ``extract_payload(cover_bytes, passphrase, format, ...) -> ExtractReport``

Both operate on bytes; the CLI wraps them with I/O. They never
touch the filesystem. The ``EmbedReport`` and ``ExtractReport``
dataclasses carry everything the CLI / TUI needs to render the
verdict (capacity, chi-square p-value, KDF parameters used,
ciphertext length, output bytes).
"""
from __future__ import annotations

import secrets
import zlib
from dataclasses import dataclass

from shared.crypto.aead import KEY_LEN, NONCE_LEN, TAG_LEN, decrypt, encrypt
from shared.crypto.kdf import (
    ARGON2_DEFAULT_MEMORY_COST, ARGON2_DEFAULT_PARALLELISM,
    ARGON2_DEFAULT_TIME_COST, SALT_LEN, argon2id,
)
from shared.crypto.secure_mem import SecureBytes
from tools.carrier import header as framing
from tools.carrier.capacity import Capacity, PayloadTooLargeError
from tools.carrier.chisquare import ChiSquareResult, chi_square
from tools.carrier.core import png as png_core
from tools.carrier.core import wav as wav_core


# Westfeld-Pfitzmann chi-square attack convention:
#   null hypothesis = "image is LSB-embedded (pair counts equal)"
#   chi-square measures deviation from that null
#   small chi2 (and HIGH p_value) -> consistent with null -> looks embedded
#   large chi2 (and LOW  p_value) -> rejects null -> looks untampered
#
# So a cover "looks tampered" when ``p_value > LSB_EMBEDDED_THRESHOLD``.
# 0.95 is the standard publication cutoff; strict mode refuses any cover
# whose p-value puts it above the line. Default mode warns; the user
# decides.
LSB_EMBEDDED_THRESHOLD = 0.95


@dataclass(slots=True)
class KdfParams:
    time_cost: int = ARGON2_DEFAULT_TIME_COST
    memory_cost: int = ARGON2_DEFAULT_MEMORY_COST
    parallelism: int = ARGON2_DEFAULT_PARALLELISM


@dataclass(slots=True)
class EmbedReport:
    output: bytes               # the stego cover (PNG or WAV bytes)
    capacity: Capacity
    chi_square: ChiSquareResult  # measured on the *input* cover
    chi_square_warn: bool        # p_value < CHI2_TAMPERED_THRESHOLD
    payload_size: int            # plaintext length
    framed_size: int             # bytes actually embedded (header + ciphertext)
    compressed: bool


@dataclass(slots=True)
class ExtractReport:
    payload: bytes               # decrypted payload bytes
    framed_size: int             # bytes read out of the cover
    compressed: bool             # whether zlib was unwrapped


class UnsupportedCoverError(ValueError):
    """Format the pipeline does not know how to handle."""


class TamperedCoverError(ValueError):
    """Cover already shows LSB tampering signature (strict mode)."""


# ---------------------------------------------------------------------------
# Format dispatch
# ---------------------------------------------------------------------------

def detect_format(data: bytes) -> str:
    """Return ``"png"`` or ``"wav"`` based on magic bytes."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "wav"
    raise UnsupportedCoverError(
        "cover format not recognised; CARRIER supports PNG and WAV"
    )


def _open_cover(data: bytes, fmt: str):
    if fmt == "png":
        return png_core.open_cover(data)
    if fmt == "wav":
        return wav_core.open_cover(data)
    raise UnsupportedCoverError(f"unsupported format: {fmt!r}")


def _capacity(cover, fmt: str, safety_factor: float | None = None) -> Capacity:
    if fmt == "png":
        return png_core.cover_capacity(cover, safety_factor=safety_factor)
    return wav_core.cover_capacity(cover, safety_factor=safety_factor)


def _lsb_samples(cover, fmt: str) -> bytes:
    return png_core.lsb_samples(cover) if fmt == "png" \
        else wav_core.lsb_samples(cover)


def _embed_into(cover, fmt: str, framed: bytes) -> bytes:
    return png_core.embed(cover, framed) if fmt == "png" \
        else wav_core.embed(cover, framed)


def _extract_from(cover, fmt: str, n_bytes: int) -> bytes:
    return png_core.extract(cover, n_bytes) if fmt == "png" \
        else wav_core.extract(cover, n_bytes)


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

def embed_payload(
    cover_bytes: bytes,
    payload: bytes,
    passphrase: bytes,
    *,
    fmt: str | None = None,
    kdf: KdfParams | None = None,
    compress: bool = True,
    safety_factor: float | None = None,
    strict_chi2: bool = False,
) -> EmbedReport:
    fmt = fmt or detect_format(cover_bytes)
    kdf = kdf or KdfParams()
    cover = _open_cover(cover_bytes, fmt)
    capacity = _capacity(cover, fmt, safety_factor=safety_factor)

    chi2_in = chi_square(_lsb_samples(cover, fmt))
    if strict_chi2 and chi2_in.p_value > LSB_EMBEDDED_THRESHOLD:
        raise TamperedCoverError(
            f"cover already shows LSB-tampering signature "
            f"(chi-square p={chi2_in.p_value:.4f} > {LSB_EMBEDDED_THRESHOLD}); "
            f"refusing in strict mode"
        )

    body = zlib.compress(payload, level=6) if compress else payload

    salt = secrets.token_bytes(SALT_LEN)
    nonce = secrets.token_bytes(NONCE_LEN)
    key_bytes = argon2id(passphrase, salt,
                         time_cost=kdf.time_cost,
                         memory_cost=kdf.memory_cost,
                         parallelism=kdf.parallelism,
                         hash_len=KEY_LEN)
    with SecureBytes(KEY_LEN) as key_buf:
        key_buf.write(key_bytes)
        ciphertext = encrypt(key_buf.bytes(), nonce, body)
    # Best-effort wipe of the local plaintext key reference.
    key_bytes = b"\x00" * KEY_LEN

    framed = framing.pack(salt, nonce, ciphertext)
    if len(framed) > capacity.safe_bytes:
        raise PayloadTooLargeError(len(framed), capacity)

    out = _embed_into(cover, fmt, framed)
    return EmbedReport(
        output=out,
        capacity=capacity,
        chi_square=chi2_in,
        chi_square_warn=chi2_in.p_value > LSB_EMBEDDED_THRESHOLD,
        payload_size=len(payload),
        framed_size=len(framed),
        compressed=compress,
    )


def extract_payload(
    cover_bytes: bytes,
    passphrase: bytes,
    *,
    fmt: str | None = None,
    kdf: KdfParams | None = None,
    compress: bool = True,
    safety_factor: float | None = None,
) -> ExtractReport:
    fmt = fmt or detect_format(cover_bytes)
    kdf = kdf or KdfParams()
    cover = _open_cover(cover_bytes, fmt)
    capacity = _capacity(cover, fmt, safety_factor=safety_factor)

    # Read just the framing header first; that tells us how much ciphertext
    # follows. Header has a hard ceiling on length so a junk cover can't
    # drive us to read past the LSB plane.
    header_bytes = _extract_from(cover, fmt, framing.HEADER_LEN)
    header = framing.read_header(header_bytes, max_bytes=capacity.safe_bytes)

    if header.length < TAG_LEN:
        raise ValueError(f"length field below GCM tag minimum")

    total = framing.HEADER_LEN + header.length
    if total > capacity.safe_bytes:
        raise ValueError(
            f"framed length {total} exceeds cover safe capacity {capacity.safe_bytes}"
        )

    raw = _extract_from(cover, fmt, total)
    ciphertext = raw[framing.HEADER_LEN:]

    key_bytes = argon2id(passphrase, header.salt,
                         time_cost=kdf.time_cost,
                         memory_cost=kdf.memory_cost,
                         parallelism=kdf.parallelism,
                         hash_len=KEY_LEN)
    with SecureBytes(KEY_LEN) as key_buf:
        key_buf.write(key_bytes)
        body = decrypt(key_buf.bytes(), header.nonce, ciphertext)
    key_bytes = b"\x00" * KEY_LEN

    if compress:
        try:
            payload = zlib.decompress(body)
            compressed = True
        except zlib.error:
            # Payload may have been embedded with --no-compress.
            payload = body
            compressed = False
    else:
        payload = body
        compressed = False

    return ExtractReport(
        payload=payload,
        framed_size=total,
        compressed=compressed,
    )


__all__ = [
    "KdfParams", "EmbedReport", "ExtractReport",
    "UnsupportedCoverError", "TamperedCoverError",
    "LSB_EMBEDDED_THRESHOLD",
    "detect_format", "embed_payload", "extract_payload",
]
