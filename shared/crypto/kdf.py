"""Key-derivation helpers -- Argon2id (passphrase) and HKDF (chain).

MASTER.md 5.3: a single source of truth for the two KDFs the suite
uses, so a future post-quantum migration replaces these wrappers
rather than crawling through callers.

``argon2id`` is for human passphrases (CARRIER cover keys, future
MASK encrypted-export keys). ``hkdf`` is for chain expansions
where the input is already high-entropy (VOID's ratchet uses HKDF
directly; STRIP and CARRIER do not need it but the helper lives
here for symmetry).
"""
from __future__ import annotations

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


# Defaults match the "interactive" class from the Argon2 RFC for
# CARRIER's typical use (local file embed, single user, no batch
# processing). Tighter classes live in MASK / future tools.
ARGON2_DEFAULT_TIME_COST = 3        # passes
ARGON2_DEFAULT_MEMORY_COST = 65536  # KiB = 64 MiB
ARGON2_DEFAULT_PARALLELISM = 4
ARGON2_DEFAULT_HASH_LEN = 32        # AES-256 key
SALT_LEN = 16                        # 128 bits, matches Argon2 RFC


def argon2id(
    passphrase: bytes,
    salt: bytes,
    *,
    time_cost: int = ARGON2_DEFAULT_TIME_COST,
    memory_cost: int = ARGON2_DEFAULT_MEMORY_COST,
    parallelism: int = ARGON2_DEFAULT_PARALLELISM,
    hash_len: int = ARGON2_DEFAULT_HASH_LEN,
) -> bytes:
    """Derive ``hash_len`` bytes from ``passphrase`` + ``salt``.

    Argon2id is the PHC-recommended memory-hard KDF; we use the
    reference implementation via ``argon2-cffi``.

    Raises ``RuntimeError`` if ``argon2-cffi`` is unavailable -- a
    clear message beats a cryptic ``ImportError`` from deep inside
    a tool.
    """
    try:
        from argon2.low_level import Type, hash_secret_raw
    except ImportError as e:  # pragma: no cover -- runtime dep
        raise RuntimeError(
            "argon2-cffi is required for passphrase-derived keys. "
            "Install with: pip install argon2-cffi>=23"
        ) from e

    if len(salt) < 8:
        raise ValueError(f"salt must be at least 8 bytes, got {len(salt)}")
    if not isinstance(passphrase, (bytes, bytearray)):
        raise TypeError("passphrase must be bytes; encode UTF-8 at the boundary")

    return hash_secret_raw(
        secret=bytes(passphrase),
        salt=bytes(salt),
        time_cost=time_cost,
        memory_cost=memory_cost,
        parallelism=parallelism,
        hash_len=hash_len,
        type=Type.ID,
    )


def hkdf(
    ikm: bytes,
    *,
    salt: bytes = b"",
    info: bytes = b"",
    length: int = 32,
) -> bytes:
    """HKDF-SHA256 derive ``length`` bytes from ``ikm``."""
    return HKDF(
        algorithm=hashes.SHA256(),
        length=length,
        salt=salt,
        info=info,
    ).derive(ikm)


__all__ = [
    "argon2id", "hkdf",
    "SALT_LEN",
    "ARGON2_DEFAULT_TIME_COST", "ARGON2_DEFAULT_MEMORY_COST",
    "ARGON2_DEFAULT_PARALLELISM", "ARGON2_DEFAULT_HASH_LEN",
]
