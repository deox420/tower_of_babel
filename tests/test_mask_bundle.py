"""Round-trip tests for MASK's encrypted identity export.

``export_blob`` seals an ``Identity`` (alias + bio + avatar PNG) under
a passphrase with Argon2id + AES-256-GCM; ``import_blob`` must recover
it byte for byte, reject a wrong passphrase with ``WrongPassphrase``,
and reject a corrupt blob with ``MalformedBlob`` before wasting an
Argon2id derivation.

Stdlib ``unittest`` only. Run with::

    python -m unittest tests.test_mask_bundle -v
"""
from __future__ import annotations

import unittest

from tools.mask.alias import AliasSpec
from tools.mask.avatar import generate_avatar
from tools.mask.bundle import (
    BUNDLE_MAGIC,
    Identity,
    MalformedBlob,
    WrongPassphrase,
    export_blob,
    import_blob,
    passphrase_as_secure,
)


def _make_identity() -> Identity:
    alias = AliasSpec(
        given="Elena", family="Cortes", handle="elena_cortes",
        locale="es", profile="default",
    )
    avatar = generate_avatar(alias.handle.encode("utf-8"))
    return Identity(alias=alias, bio="De provincias.", avatar=avatar, mail=None)


class MaskBundleRoundTripTests(unittest.TestCase):
    def test_export_import_round_trip(self) -> None:
        ident = _make_identity()
        with passphrase_as_secure(b"open sesame") as pw:
            blob = export_blob(ident, pw)
        self.assertTrue(blob.startswith(BUNDLE_MAGIC))

        with passphrase_as_secure(b"open sesame") as pw:
            restored = import_blob(blob, pw)

        self.assertEqual(restored.to_dict(), ident.to_dict())
        # The avatar PNG bytes survive the round-trip (carried inside the AEAD).
        self.assertEqual(restored.avatar.png_bytes, ident.avatar.png_bytes)

    def test_wrong_passphrase_rejected(self) -> None:
        ident = _make_identity()
        with passphrase_as_secure(b"right one") as pw:
            blob = export_blob(ident, pw)
        with passphrase_as_secure(b"wrong one") as pw:
            with self.assertRaises(WrongPassphrase):
                import_blob(blob, pw)

    def test_malformed_blob_rejected_before_kdf(self) -> None:
        with passphrase_as_secure(b"whatever") as pw:
            with self.assertRaises(MalformedBlob):
                import_blob(b"not a real blob", pw)            # bad magic / short
            with self.assertRaises(MalformedBlob):
                import_blob(b"WRNG" + b"\x00" * 64, pw)        # wrong magic

    def test_empty_passphrase_refused(self) -> None:
        with self.assertRaises(ValueError):
            passphrase_as_secure(b"")

    def test_zeroize_drops_avatar_and_mail(self) -> None:
        ident = _make_identity()
        self.assertTrue(ident.avatar.png_bytes)
        ident.zeroize()
        self.assertEqual(set(ident.avatar.png_bytes), {0})
        self.assertIsNone(ident.mail)


if __name__ == "__main__":
    unittest.main()
