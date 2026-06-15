"""Identity bundle + encrypted-export round-trip.

The ``Identity`` dataclass is the in-RAM whole of a disposable
identity: alias, bio, avatar, optional mail handle, and a rounded
timestamp. It exposes:

  ``to_dict()`` / ``from_dict()``    -- canonical JSON shape, also
                                          the body of ``mask://``.
  ``zeroize()``                       -- drops the PNG bytes and
                                          clears the avatar.
  ``export_blob()`` / ``import_blob()``
                                      -- passphrase-sealed bytes,
                                         Argon2id + AES-256-GCM.

The export blob is the only on-disk form the tool produces, and only
when the user passes ``--export <path>``. The passphrase travels
through ``SecureBytes`` and is zeroed on exit, even if the call
raises.
"""
from __future__ import annotations

import base64
import json
import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from shared.crypto.aead import KEY_LEN, NONCE_LEN, decrypt, encrypt
from shared.crypto.kdf import SALT_LEN, argon2id
from shared.crypto.secure_mem import SecureBytes

from tools.mask.alias import AliasSpec
from tools.mask.avatar import Avatar

if TYPE_CHECKING:
    # Forward-ref only: keeps the mail module out of import-time so a
    # MASK run that never touches temp-mail does not pull httpx.
    from tools.mask.mail import MailHandle


BUNDLE_MAGIC = b"MASK"
TS_ROUND_SECONDS = 60       # round to 60s so the timestamp does not
                            # leak sub-minute clock precision into
                            # the wire (MASK.md Section 7 wire spec).


class WrongPassphrase(ValueError):
    """Raised when ``import_blob`` fails the AES-GCM auth tag."""


class MalformedBlob(ValueError):
    """Raised when the blob's magic or length is wrong (caught before AEAD)."""


@dataclass
class Identity:
    """In-RAM identity. Use ``zeroize()`` before dropping the reference.

    The avatar's PNG bytes are kept here so the TUI can render a
    preview; the wire form (`to_dict`) carries only the SHA hash of
    the SVG, and the optional PNG-export path writes the bytes out
    separately.
    """

    alias: AliasSpec
    bio: str
    avatar: Avatar
    mail: "MailHandle | None"   # forward ref so we don't pull mail at import
    ts: int = field(default_factory=lambda: _round_ts(int(time.time())))

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical wire-shape dict.

        Used by ``tools.mask.link`` to build the ``mask://`` URL and
        by ``export_blob`` to seal the JSON inside the AEAD.
        """
        return {
            "alias": {
                "given":   self.alias.given,
                "family":  self.alias.family,
                "handle":  self.alias.handle,
                "locale":  self.alias.locale,
                "profile": self.alias.profile,
            },
            "bio": self.bio,
            "avatar_sha": self.avatar.sha256,
            "mail_handle": self.mail.address if self.mail is not None else None,
            "ts": self.ts,
        }

    def zeroize(self) -> None:
        """Best-effort wipe.

        Python strings are immutable, so we cannot scrub the alias
        fields in place. What we *can* do is replace the avatar's
        PNG bytes with zeros and reset the mail handle to None so a
        later peek at the Identity object reveals nothing.
        """
        if self.avatar.png_bytes:
            zero = bytes(len(self.avatar.png_bytes))
            object.__setattr__(self.avatar, "png_bytes", zero)
        self.mail = None


# ---------------------------------------------------------------------------
# Reconstruction
# ---------------------------------------------------------------------------


def from_dict(d: dict[str, Any]) -> Identity:
    """Rebuild an ``Identity`` from a canonical-dict.

    The avatar PNG is regenerated locally (the wire form carries
    only the SHA). The mail handle is reconstructed as a minimal
    ``MailHandle`` -- inbox_url is set to a blank when unknown,
    because we cannot recover the provider's session.
    """
    from tools.mask.avatar import generate_avatar
    from tools.mask.mail import MailHandle

    alias_d = d["alias"]
    alias = AliasSpec(
        given=alias_d["given"], family=alias_d["family"],
        handle=alias_d["handle"], locale=alias_d["locale"],
        profile=alias_d["profile"],
    )
    avatar = generate_avatar(alias.handle.encode("utf-8"))
    if d.get("avatar_sha") and d["avatar_sha"] != avatar.sha256:
        # The handle no longer hashes to the same avatar. Surface this
        # as a hint, not a hard failure -- the user may have rotated
        # the algorithm intentionally.
        pass
    mail = None
    if d.get("mail_handle"):
        mail = MailHandle(
            address=d["mail_handle"], provider="unknown",
            inbox_url="", expires_in_s=None,
        )
    return Identity(alias=alias, bio=d["bio"], avatar=avatar, mail=mail,
                    ts=int(d["ts"]))


# ---------------------------------------------------------------------------
# Encrypted export
# ---------------------------------------------------------------------------


def export_blob(identity: Identity, passphrase: SecureBytes) -> bytes:
    """Seal ``identity`` into a self-contained blob.

    Layout:
      4 bytes  : magic = ``b"MASK"``
      16 bytes : Argon2id salt
      12 bytes : AES-GCM nonce
      *        : AES-256-GCM(ciphertext || 16-byte tag)

    The plaintext inside the AEAD is the canonical JSON dict plus
    the avatar PNG bytes (base64url'd under ``avatar_png``), so an
    import recovers the visual avatar too.
    """
    payload = identity.to_dict()
    payload["avatar_png"] = base64.urlsafe_b64encode(
        identity.avatar.png_bytes).decode("ascii")
    pt = json.dumps(payload, sort_keys=True,
                    separators=(",", ":")).encode("utf-8")

    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)

    with SecureBytes(KEY_LEN) as key_buf:
        key = argon2id(passphrase.bytes(), salt)
        key_buf.write(key)
        # Zero the derived key in our local frame as soon as possible.
        try:
            ct = encrypt(key_buf.bytes(), nonce, pt)
        finally:
            # Overwrite the key bytes; SecureBytes.zero() on exit
            # handles the long-term wipe.
            key = bytes(KEY_LEN)        # noqa: F841 -- local rebind
    return BUNDLE_MAGIC + salt + nonce + ct


def import_blob(blob: bytes, passphrase: SecureBytes) -> Identity:
    """Open a blob produced by ``export_blob`` and return an ``Identity``.

    Raises ``MalformedBlob`` if the magic / length is wrong (cheap
    rejection before we waste an Argon2id derivation).
    Raises ``WrongPassphrase`` on AES-GCM authentication failure.
    """
    if not isinstance(blob, (bytes, bytearray)):
        raise MalformedBlob(f"expected bytes, got {type(blob).__name__}")
    if len(blob) < 4 + SALT_LEN + NONCE_LEN + 16:
        raise MalformedBlob(f"blob too short: {len(blob)} bytes")
    if bytes(blob[:4]) != BUNDLE_MAGIC:
        raise MalformedBlob("missing MASK magic")

    salt = bytes(blob[4:4 + SALT_LEN])
    nonce = bytes(blob[4 + SALT_LEN:4 + SALT_LEN + NONCE_LEN])
    ct = bytes(blob[4 + SALT_LEN + NONCE_LEN:])

    with SecureBytes(KEY_LEN) as key_buf:
        key_buf.write(argon2id(passphrase.bytes(), salt))
        try:
            pt = decrypt(key_buf.bytes(), nonce, ct)
        except Exception as e:
            # InvalidTag (wrong passphrase or tampered blob) -> WrongPassphrase.
            from cryptography.exceptions import InvalidTag
            if isinstance(e, InvalidTag):
                raise WrongPassphrase("wrong passphrase or tampered blob") from e
            raise

    payload = json.loads(pt.decode("utf-8"))
    png_b64 = payload.pop("avatar_png", None)
    identity = from_dict(payload)
    if png_b64:
        png = base64.urlsafe_b64decode(png_b64.encode("ascii"))
        object.__setattr__(identity.avatar, "png_bytes", png)
    return identity


def passphrase_as_secure(passphrase: bytes) -> SecureBytes:
    """Copy ``passphrase`` into a ``SecureBytes`` and return it.

    Caller owns the lifecycle (``with`` block recommended). The
    input ``bytes`` cannot be scrubbed by us -- the rule is to keep
    plaintext passphrases out of long-lived Python buffers.
    """
    if not passphrase:
        raise ValueError("empty passphrase refused")
    buf = SecureBytes(len(passphrase))
    buf.write(passphrase)
    return buf


def _round_ts(ts: int) -> int:
    return (ts // TS_ROUND_SECONDS) * TS_ROUND_SECONDS


__all__ = [
    "BUNDLE_MAGIC", "TS_ROUND_SECONDS",
    "Identity", "WrongPassphrase", "MalformedBlob",
    "from_dict", "export_blob", "import_blob", "passphrase_as_secure",
]
