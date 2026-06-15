"""X3DH + Double Ratchet primitives for VOID.

We never re-implement cryptography. Symmetric primitives come from
``cryptography`` (AES-GCM, HKDF); X25519/Ed25519 from ``xeddsa``;
state-machine plumbing from ``doubleratchet`` and ``x3dh``.

Public surface:

- :class:`Identity` — holds our Ed25519 IK seed and an ``x3dh.State``.
- :func:`new_identity` — generate a fresh identity and 10 OPKs.
- :func:`serialise_bundle` / :func:`deserialise_bundle`
- :class:`Handshake` namespace — active and passive X3DH + DR bootstrap.
- :class:`Ratchet` namespace — encrypt/decrypt with an established DR.
- :func:`sign_blob` / :func:`verify_blob` — Ed25519 over (header || ct).
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from typing import Tuple

import xeddsa
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .secure_mem import SecureBytes

from doubleratchet.aead import (
    AEAD,
    AuthenticationFailedException,
    DecryptionFailedException,
)
from doubleratchet.diffie_hellman_ratchet import DiffieHellmanRatchet
from doubleratchet.double_ratchet import DoubleRatchet as DoubleRatchetBase
from doubleratchet.kdf import KDF
from doubleratchet.types import Header as DRHeader, EncryptedMessage

from x3dh.identity_key_pair import IdentityKeyPairSeed
from x3dh.state import State
from x3dh.types import Bundle, Header as X3DHHeader, IdentityKeyFormat
from x3dh.crypto_provider import HashFunction


class VoidX3DHState(State):
    """Concrete x3dh.State. Bundles live in RAM; no persistence callback needed."""

    def _publish_bundle(self, bundle: Bundle) -> None:
        # Called by the library whenever the bundle changes (rotation, refill).
        # The VOID client checks state.bundle directly when uploading; nothing to do here.
        return

    @staticmethod
    def _encode_public_key(key_format: IdentityKeyFormat, pub: bytes) -> bytes:
        # 1-byte tag so two different curves can never collide, plus raw key bytes.
        tag = b"\x01" if key_format is IdentityKeyFormat.ED_25519 else b"\x02"
        return tag + pub


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INFO = b"VOID-X3DH-v3"
ROOT_INFO = b"VOID-Root"
IV_INFO = b"VOID-IV"
MSG_CHAIN_CONSTANT = b"\x01"
MAX_SKIPPED_KEYS = 1000
DOS_PROTECTION_THRESHOLD = 100
ASSOC_DATA_BASE = b"VOID-v3-AD"


# ---------------------------------------------------------------------------
# AEAD: AES-256-GCM with key-derived IV (per-message key is unique → safe)
# ---------------------------------------------------------------------------


class VoidAEAD(AEAD):
    @staticmethod
    async def encrypt(plaintext: bytes, key: bytes, associated_data: bytes) -> bytes:
        enc_key, iv = VoidAEAD._derive(key)
        return AESGCM(enc_key).encrypt(iv, plaintext, associated_data)

    @staticmethod
    async def decrypt(ciphertext: bytes, key: bytes, associated_data: bytes) -> bytes:
        enc_key, iv = VoidAEAD._derive(key)
        try:
            return AESGCM(enc_key).decrypt(iv, ciphertext, associated_data)
        except InvalidTag as e:
            raise AuthenticationFailedException(str(e)) from e
        except Exception as e:
            raise DecryptionFailedException(str(e)) from e

    @staticmethod
    def _derive(key: bytes) -> Tuple[bytes, bytes]:
        # HKDF expands the chain key into 32B AES key + 12B IV.
        out = HKDF(
            algorithm=hashes.SHA256(),
            length=44,
            salt=b"\x00" * 32,
            info=IV_INFO,
        ).derive(key)
        return out[:32], out[32:44]


# ---------------------------------------------------------------------------
# Root- and message-chain KDFs (HKDF-SHA256)
# ---------------------------------------------------------------------------


class VoidRootKDF(KDF):
    @staticmethod
    async def derive(key: bytes, data: bytes, length: int) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=key,
            info=ROOT_INFO,
        ).derive(data)


class VoidMessageKDF(KDF):
    @staticmethod
    async def derive(key: bytes, data: bytes, length: int) -> bytes:
        return HKDF(
            algorithm=hashes.SHA256(),
            length=length,
            salt=key,
            info=b"VOID-Msg",
        ).derive(data)


# ---------------------------------------------------------------------------
# DH ratchet: X25519
# ---------------------------------------------------------------------------


class VoidDR(DiffieHellmanRatchet):
    @staticmethod
    def _generate_priv() -> bytes:
        # X25519 private = 32 random bytes (xeddsa clamps internally when needed).
        return secrets.token_bytes(32)

    @staticmethod
    def _derive_pub(priv: bytes) -> bytes:
        return bytes(xeddsa.priv_to_curve25519_pub(priv))

    @staticmethod
    def _perform_diffie_hellman(own_priv: bytes, other_pub: bytes) -> bytes:
        return bytes(xeddsa.x25519(own_priv, other_pub))


# ---------------------------------------------------------------------------
# DoubleRatchet subclass wired up with our primitives
# ---------------------------------------------------------------------------


class VoidDoubleRatchet(DoubleRatchetBase):
    @staticmethod
    def _build_associated_data(associated_data: bytes, header: DRHeader) -> bytes:
        # Bind every ciphertext to the caller-supplied AD AND the ratchet header.
        # Lengths are encoded so the result parses uniquely.
        ad = associated_data
        rpub = header.ratchet_pub
        n = int(header.sending_chain_length).to_bytes(4, "big")
        pn = int(header.previous_sending_chain_length).to_bytes(4, "big")
        return (
            len(ad).to_bytes(4, "big") + ad
            + len(rpub).to_bytes(2, "big") + rpub
            + n + pn
        )


_DR_KWARGS = dict(
    diffie_hellman_ratchet_class=VoidDR,
    root_chain_kdf=VoidRootKDF,
    message_chain_kdf=VoidMessageKDF,
    message_chain_constant=MSG_CHAIN_CONSTANT,
    dos_protection_threshold=DOS_PROTECTION_THRESHOLD,
    max_num_skipped_message_keys=MAX_SKIPPED_KEYS,
    aead=VoidAEAD,
)


# ---------------------------------------------------------------------------
# Identity: Ed25519 IK seed + x3dh.State
# ---------------------------------------------------------------------------


class Identity:
    """Holds the Ed25519 seed in an mlock'd buffer plus the x3dh State."""

    __slots__ = ("_seed", "ik_pub", "state")

    def __init__(self, seed: SecureBytes, ik_pub: bytes, state: State) -> None:
        self._seed = seed
        self.ik_pub = ik_pub
        self.state = state

    @property
    def fp8(self) -> str:
        return hashlib.sha256(self.ik_pub).hexdigest()[:8]

    @property
    def fp_full(self) -> str:
        return hashlib.sha256(self.ik_pub).hexdigest()

    def seed_bytes(self) -> bytes:
        """Transient copy of the Ed25519 seed. Caller must not retain it."""
        return self._seed.bytes()

    def destroy(self) -> None:
        try:
            self._seed.free()
        except Exception:
            pass


def new_identity(num_opks: int = 10) -> Identity:
    raw = secrets.token_bytes(32)
    seed = SecureBytes(32)
    seed.write(raw)
    # Wipe the local raw copy as soon as possible.
    raw = b"\x00" * 32
    seed_view = seed.bytes()
    ik_pub = bytes(xeddsa.seed_to_ed25519_pub(seed_view))
    state = VoidX3DHState.create(
        identity_key_format=IdentityKeyFormat.ED_25519,
        hash_function=HashFunction.SHA_256,
        info=INFO,
        identity_key_pair=IdentityKeyPairSeed(seed_view),
    )
    seed_view = b"\x00" * 32  # drop the transient bytes copy
    state.generate_pre_keys(num_opks)
    return Identity(seed=seed, ik_pub=ik_pub, state=state)


# ---------------------------------------------------------------------------
# Signatures (Ed25519 via xeddsa.ed25519_seed_sign / ed25519_verify)
# ---------------------------------------------------------------------------


def sign_blob(seed: bytes, payload: bytes) -> bytes:
    return bytes(xeddsa.ed25519_seed_sign(seed, payload))


def sign_with_identity(identity: Identity, payload: bytes) -> bytes:
    seed_bytes = identity.seed_bytes()
    try:
        return sign_blob(seed_bytes, payload)
    finally:
        seed_bytes = b"\x00" * len(seed_bytes)


def verify_blob(ik_pub: bytes, sig: bytes, payload: bytes) -> bool:
    try:
        return bool(xeddsa.ed25519_verify(sig, ik_pub, payload))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Wire-format serialisers (bundles, headers, encrypted messages)
# ---------------------------------------------------------------------------


def _b64e(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _b64d(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"), validate=True)


def serialise_bundle(b: Bundle) -> dict:
    return {
        "ik": _b64e(b.identity_key),
        "spk": _b64e(b.signed_pre_key),
        "spk_sig": _b64e(b.signed_pre_key_sig),
        "opks": [_b64e(p) for p in b.pre_keys],
    }


def deserialise_bundle(d: dict) -> Bundle:
    return Bundle(
        identity_key=_b64d(d["ik"]),
        signed_pre_key=_b64d(d["spk"]),
        signed_pre_key_sig=_b64d(d["spk_sig"]),
        pre_keys=frozenset(_b64d(p) for p in d["opks"]),
    )


def serialise_x3dh_header(h: X3DHHeader) -> dict:
    out = {
        "ik": _b64e(h.identity_key),
        "ek": _b64e(h.ephemeral_key),
        "spk": _b64e(h.signed_pre_key),
    }
    if h.pre_key is not None:
        out["opk"] = _b64e(h.pre_key)
    return out


def deserialise_x3dh_header(d: dict) -> X3DHHeader:
    return X3DHHeader(
        identity_key=_b64d(d["ik"]),
        ephemeral_key=_b64d(d["ek"]),
        signed_pre_key=_b64d(d["spk"]),
        pre_key=_b64d(d["opk"]) if "opk" in d else None,
    )


def serialise_dr_message(em: EncryptedMessage) -> dict:
    return {
        "rpub": _b64e(em.header.ratchet_pub),
        "n": em.header.sending_chain_length,
        "pn": em.header.previous_sending_chain_length,
        "ct": _b64e(em.ciphertext),
    }


def deserialise_dr_message(d: dict) -> EncryptedMessage:
    header = DRHeader(
        ratchet_pub=_b64d(d["rpub"]),
        sending_chain_length=int(d["n"]),
        previous_sending_chain_length=int(d["pn"]),
    )
    return EncryptedMessage(header=header, ciphertext=_b64d(d["ct"]))


# ---------------------------------------------------------------------------
# Associated data construction (binds DR ciphertext to both identities)
# ---------------------------------------------------------------------------


def assoc_data(sender_ik: bytes, recipient_ik: bytes) -> bytes:
    return ASSOC_DATA_BASE + sender_ik + recipient_ik


# ---------------------------------------------------------------------------
# Handshake (Active = initiator side; Passive = responder side)
# ---------------------------------------------------------------------------


async def handshake_active(
    our_identity: Identity,
    peer_bundle: Bundle,
    plaintext: bytes,
) -> Tuple[VoidDoubleRatchet, X3DHHeader, EncryptedMessage]:
    """Run active X3DH against ``peer_bundle`` and produce the initial DR ciphertext.

    Raises ``KeyAgreementException`` (from x3dh) or
    ``cryptography.exceptions.*`` on irrecoverable failure.
    """
    shared_secret, x3dh_ad, x3dh_header = await our_identity.state.get_shared_secret_active(
        peer_bundle, associated_data_appendix=b"", require_pre_key=True
    )
    ad = assoc_data(our_identity.ik_pub, peer_bundle.identity_key)
    dr, encrypted = await VoidDoubleRatchet.encrypt_initial_message(
        **_DR_KWARGS,
        shared_secret=shared_secret,
        recipient_ratchet_pub=peer_bundle.signed_pre_key,
        message=plaintext,
        associated_data=ad,
    )
    return dr, x3dh_header, encrypted


async def handshake_passive(
    our_identity: Identity,
    x3dh_header: X3DHHeader,
    encrypted: EncryptedMessage,
) -> Tuple[VoidDoubleRatchet, bytes]:
    """Receive a ``ratchet_init`` frame: derive SK passively and decrypt the initial DR message."""
    shared_secret, x3dh_ad, signed_pre_key_pair = await our_identity.state.get_shared_secret_passive(
        x3dh_header, associated_data_appendix=b"", require_pre_key=True
    )
    ad = assoc_data(x3dh_header.identity_key, our_identity.ik_pub)
    dr, plaintext = await VoidDoubleRatchet.decrypt_initial_message(
        **_DR_KWARGS,
        shared_secret=shared_secret,
        own_ratchet_priv=signed_pre_key_pair.priv,
        message=encrypted,
        associated_data=ad,
    )
    return dr, plaintext


async def ratchet_encrypt(
    dr: VoidDoubleRatchet,
    sender_ik: bytes,
    recipient_ik: bytes,
    plaintext: bytes,
) -> EncryptedMessage:
    ad = assoc_data(sender_ik, recipient_ik)
    return await dr.encrypt_message(plaintext, ad)


async def ratchet_decrypt(
    dr: VoidDoubleRatchet,
    sender_ik: bytes,
    recipient_ik: bytes,
    encrypted: EncryptedMessage,
) -> bytes:
    ad = assoc_data(sender_ik, recipient_ik)
    return await dr.decrypt_message(encrypted, ad)
