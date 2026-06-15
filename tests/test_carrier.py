"""Round-trip tests for the CARRIER steganography pipeline.

Covers the public ``embed_payload`` / ``extract_payload`` surface end
to end: a payload sealed with AES-256-GCM (Argon2id-derived key) and
hidden in the LSB plane of an in-memory PNG cover must come back byte
identical, and a wrong passphrase or a too-large payload must be
rejected.

Stdlib ``unittest`` only. Run with::

    python -m unittest tests.test_carrier -v

Argon2id runs at minimum cost so the suite stays fast.
"""
from __future__ import annotations

import io
import os
import unittest

from cryptography.exceptions import InvalidTag

from tools.carrier.capacity import PayloadTooLargeError
from tools.carrier.pipeline import (
    KdfParams,
    embed_payload,
    extract_payload,
)

try:
    from PIL import Image
    _HAVE_PIL = True
except ImportError:  # pragma: no cover - Pillow is a hard dep
    _HAVE_PIL = False


_FAST_KDF = KdfParams(time_cost=1, memory_cost=8, parallelism=1)


def _noise_png(width: int = 128, height: int = 128) -> bytes:
    """A noisy RGB PNG: noise keeps the LSB plane non-degenerate so the
    chi-square sampler has something realistic to chew on."""
    img = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@unittest.skipUnless(_HAVE_PIL, "Pillow not installed")
class CarrierRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cover = _noise_png()
        self.passphrase = b"correct horse battery staple"

    def test_round_trip(self) -> None:
        payload = b"the eagle lands at midnight; rendezvous at pier 9"
        emb = embed_payload(self.cover, payload, self.passphrase, kdf=_FAST_KDF)
        self.assertNotEqual(emb.output, self.cover)
        self.assertEqual(emb.payload_size, len(payload))
        ext = extract_payload(emb.output, self.passphrase, kdf=_FAST_KDF)
        self.assertEqual(ext.payload, payload)

    def test_round_trip_no_compress(self) -> None:
        payload = b"\x00\x01\x02\x03 binary-ish payload \xff\xfe"
        emb = embed_payload(self.cover, payload, self.passphrase,
                            kdf=_FAST_KDF, compress=False)
        ext = extract_payload(emb.output, self.passphrase,
                              kdf=_FAST_KDF, compress=False)
        self.assertEqual(ext.payload, payload)

    def test_wrong_passphrase_rejected(self) -> None:
        emb = embed_payload(self.cover, b"secret", self.passphrase, kdf=_FAST_KDF)
        with self.assertRaises(InvalidTag):
            extract_payload(emb.output, b"not the passphrase", kdf=_FAST_KDF)

    def test_payload_too_large_rejected(self) -> None:
        # 128x128 RGB safe-capacity is well under 64 KiB of random bytes.
        too_big = os.urandom(64 * 1024)
        with self.assertRaises(PayloadTooLargeError):
            embed_payload(self.cover, too_big, self.passphrase, kdf=_FAST_KDF)

    def test_stego_output_is_valid_png(self) -> None:
        emb = embed_payload(self.cover, b"hi", self.passphrase, kdf=_FAST_KDF)
        # The carrier must hand back a still-openable image.
        img = Image.open(io.BytesIO(emb.output))
        self.assertEqual(img.size, (128, 128))


if __name__ == "__main__":
    unittest.main()
