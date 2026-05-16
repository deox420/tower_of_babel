"""Client-side helpers: ASCII validation, padding, plaintext JSON wrapper.

The symmetric key derivation that Phase 2 used (PBKDF2 → HKDF rotation)
is REMOVED. Phase 3 replaces it with X3DH + Double Ratchet (see
:mod:`client.ratchet`). Padding and the plaintext envelope are still
applied here BEFORE handing bytes to the ratchet for encryption.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets

GCM_TAG = 16

PAD_BLOCK = 1024
MAX_PLAINTEXT = 8 * 1024
MAX_CIPHERTEXT = MAX_PLAINTEXT + GCM_TAG  # 8208

PROTO_VERSION = 3


def b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def derive_room_id(room_key: str) -> str:
    """Opaque room identifier the server sees; the room_key itself never leaves."""
    return hashlib.sha256(room_key.encode("utf-8")).hexdigest()[:16]


def zero_bytes(b: "bytearray | bytes | None") -> None:
    if isinstance(b, bytearray):
        for i in range(len(b)):
            b[i] = 0


# --- ISO/IEC 7816-4 padding -------------------------------------------------


def pad_iso7816(data: bytes, block: int = PAD_BLOCK) -> bytes:
    pad_len = block - (len(data) % block)
    return data + b"\x80" + (b"\x00" * (pad_len - 1))


def unpad_iso7816(data: bytes) -> bytes | None:
    if not data:
        return None
    i = data.rfind(b"\x80")
    if i < 0:
        return None
    if data[i + 1 :] != b"\x00" * (len(data) - i - 1):
        return None
    return data[:i]


# --- Plaintext envelope -----------------------------------------------------


def encode_plaintext_text(text: str) -> bytes:
    return json.dumps({"v": PROTO_VERSION, "text": text}, separators=(",", ":")).encode("utf-8")


def encode_plaintext_dummy() -> bytes:
    noise_len = secrets.randbelow(900) + 50
    noise = base64.b64encode(secrets.token_bytes(noise_len))[:noise_len].decode("ascii")
    return json.dumps(
        {"v": PROTO_VERSION, "dummy": True, "noise": noise}, separators=(",", ":")
    ).encode("utf-8")


def encode_plaintext_hello() -> bytes:
    """Initial payload of a ratchet_init frame; receivers don't render it."""
    return json.dumps({"v": PROTO_VERSION, "hello": True}, separators=(",", ":")).encode("utf-8")


def decode_plaintext(blob: bytes) -> dict | None:
    try:
        obj = json.loads(blob.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(obj, dict) or obj.get("v") != PROTO_VERSION:
        return None
    return obj


def fingerprint8(ik_pub: bytes) -> str:
    return hashlib.sha256(ik_pub).hexdigest()[:8]


def fingerprint_full(ik_pub: bytes) -> str:
    return hashlib.sha256(ik_pub).hexdigest()
