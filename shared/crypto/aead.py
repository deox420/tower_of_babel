"""AES-256-GCM AEAD helper -- single thin wrapper used across tools.

MASTER.md 5.2: VOID already uses ``AESGCM`` directly through its
ratchet; CARRIER does its own one-shot embed. Both reach for the
same primitive; centralising the call site means one audit point
for the cipher, not N.

This is intentionally a small surface: encrypt / decrypt, with the
GCM tag glued onto the ciphertext (``cryptography``'s default).
Nonce management is the caller's responsibility -- we don't generate
the nonce, we don't store it, and we never reuse it.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_LEN = 32   # AES-256
NONCE_LEN = 12  # GCM-recommended IV length
TAG_LEN = 16   # GCM tag size, appended by cryptography


def encrypt(key: bytes, nonce: bytes, plaintext: bytes,
            associated_data: bytes | None = None) -> bytes:
    """AES-256-GCM seal. Returns ``ciphertext || tag``.

    Raises ``ValueError`` for wrong-sized key or nonce. The caller
    guarantees the (key, nonce) pair is unique across all encryptions
    with that key.
    """
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"nonce must be {NONCE_LEN} bytes, got {len(nonce)}")
    return AESGCM(key).encrypt(nonce, plaintext, associated_data)


def decrypt(key: bytes, nonce: bytes, ciphertext: bytes,
            associated_data: bytes | None = None) -> bytes:
    """AES-256-GCM open. Raises ``cryptography.exceptions.InvalidTag``
    on authentication failure (wrong key, tampered ciphertext, or
    mismatched associated data).
    """
    if len(key) != KEY_LEN:
        raise ValueError(f"key must be {KEY_LEN} bytes, got {len(key)}")
    if len(nonce) != NONCE_LEN:
        raise ValueError(f"nonce must be {NONCE_LEN} bytes, got {len(nonce)}")
    return AESGCM(key).decrypt(nonce, ciphertext, associated_data)


__all__ = ["encrypt", "decrypt", "KEY_LEN", "NONCE_LEN", "TAG_LEN"]
