"""CARRIER payload framing (no magic, GCM-tag-as-validity).

Layout::

    +-------------+-------------+-----------------+----------------+
    | salt 16 B   | nonce 12 B  | length 4 B (BE) | ciphertext + tag
    +-------------+-------------+-----------------+----------------+

Total fixed overhead is 32 bytes; the ciphertext carries a 16-byte
GCM tag at the end. No magic field: the GCM authentication is the
signal. Extracting from a plain (non-CARRIER) cover reads 32 random
bytes as salt/nonce/length, runs Argon2id (slow, by design), and
fails the GCM tag check. That gives an informed adversary no
faster signal than guessing passphrases.

Note: the length field has to fit inside the cover's safe capacity,
which the caller enforces -- a malicious cover with `length = 2^32-1`
would otherwise drive the extractor to try to read past the LSB
plane. ``read_header`` rejects lengths above an explicit ``max_bytes``.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass

from shared.crypto.aead import NONCE_LEN, TAG_LEN
from shared.crypto.kdf import SALT_LEN


VERSION = 1
LENGTH_FIELD = 4
HEADER_LEN = SALT_LEN + NONCE_LEN + LENGTH_FIELD  # 16 + 12 + 4 = 32


@dataclass(slots=True)
class Header:
    salt: bytes
    nonce: bytes
    length: int  # ciphertext length in bytes (includes GCM tag)


def pack(salt: bytes, nonce: bytes, ciphertext: bytes) -> bytes:
    """Concatenate the framing for an embed.

    Returns ``salt || nonce || length || ciphertext``. The output
    length is ``HEADER_LEN + len(ciphertext)``.
    """
    if len(salt) != SALT_LEN:
        raise ValueError(f"salt must be {SALT_LEN} bytes")
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"nonce must be {NONCE_LEN} bytes")
    if len(ciphertext) < TAG_LEN:
        raise ValueError(f"ciphertext must be at least {TAG_LEN} bytes (GCM tag)")
    return salt + nonce + struct.pack(">I", len(ciphertext)) + ciphertext


def read_header(buf: bytes, *, max_bytes: int) -> Header:
    """Parse the fixed 32-byte header from the start of ``buf``.

    ``max_bytes`` is the cover's safe-capacity in bytes; the parsed
    length is clamped against it so a tampered or random cover
    can't drive the extractor to read past the LSB plane.

    Raises ``ValueError`` if the buffer is too short or the length
    field exceeds ``max_bytes``.
    """
    if len(buf) < HEADER_LEN:
        raise ValueError(
            f"buffer too short for header ({len(buf)} < {HEADER_LEN})"
        )
    salt = buf[:SALT_LEN]
    nonce = buf[SALT_LEN:SALT_LEN + NONCE_LEN]
    length = struct.unpack(
        ">I", buf[SALT_LEN + NONCE_LEN:SALT_LEN + NONCE_LEN + LENGTH_FIELD]
    )[0]
    if length < TAG_LEN:
        raise ValueError(f"length field {length} below GCM tag minimum")
    if length > max_bytes:
        raise ValueError(
            f"length field {length} exceeds cover safe capacity {max_bytes}"
        )
    return Header(salt=salt, nonce=nonce, length=length)


__all__ = ["Header", "HEADER_LEN", "VERSION", "pack", "read_header"]
