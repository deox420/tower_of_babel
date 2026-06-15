"""Tests for the shared crypto primitives.

MASTER.md 5.2/5.3 call ``shared.crypto`` the suite's single audit
point for the cipher and the two KDFs, so these wrappers carry the
weight for CARRIER, MASK, and VOID alike. They had no coverage; this
module exercises the round-trips, the input guards, and the
tamper/wrong-key rejection paths.

Stdlib ``unittest`` only (the repo ships no pytest). Run with::

    python -m unittest tests.test_crypto -v

Argon2id is invoked at the smallest sane cost so the suite stays
fast and deterministic.
"""
from __future__ import annotations

import os
import unittest

from cryptography.exceptions import InvalidTag

from shared.crypto import aead, kdf
from shared.crypto.secure_mem import SecureBytes, mlock_status, swap_active


# Cheap Argon2 parameters: keep the determinism tests sub-second.
_FAST = dict(time_cost=1, memory_cost=8, parallelism=1)


class AeadTests(unittest.TestCase):
    def setUp(self) -> None:
        self.key = os.urandom(aead.KEY_LEN)
        self.nonce = os.urandom(aead.NONCE_LEN)

    def test_constants(self) -> None:
        self.assertEqual(aead.KEY_LEN, 32)
        self.assertEqual(aead.NONCE_LEN, 12)
        self.assertEqual(aead.TAG_LEN, 16)

    def test_round_trip(self) -> None:
        pt = b"the eagle lands at midnight"
        ct = aead.encrypt(self.key, self.nonce, pt)
        # ciphertext == plaintext length + GCM tag.
        self.assertEqual(len(ct), len(pt) + aead.TAG_LEN)
        self.assertNotEqual(ct[:len(pt)], pt)
        self.assertEqual(aead.decrypt(self.key, self.nonce, ct), pt)

    def test_round_trip_with_aad(self) -> None:
        pt = b"payload"
        aad = b"v2-header"
        ct = aead.encrypt(self.key, self.nonce, pt, aad)
        self.assertEqual(aead.decrypt(self.key, self.nonce, ct, aad), pt)

    def test_empty_plaintext_round_trips(self) -> None:
        ct = aead.encrypt(self.key, self.nonce, b"")
        self.assertEqual(aead.decrypt(self.key, self.nonce, ct), b"")

    def test_wrong_aad_rejected(self) -> None:
        ct = aead.encrypt(self.key, self.nonce, b"x", b"good-aad")
        with self.assertRaises(InvalidTag):
            aead.decrypt(self.key, self.nonce, ct, b"bad-aad")

    def test_wrong_key_rejected(self) -> None:
        ct = aead.encrypt(self.key, self.nonce, b"secret")
        other = os.urandom(aead.KEY_LEN)
        with self.assertRaises(InvalidTag):
            aead.decrypt(other, self.nonce, ct)

    def test_tampered_ciphertext_rejected(self) -> None:
        ct = bytearray(aead.encrypt(self.key, self.nonce, b"secret"))
        ct[0] ^= 0x01
        with self.assertRaises(InvalidTag):
            aead.decrypt(self.key, self.nonce, bytes(ct))

    def test_bad_key_length_rejected(self) -> None:
        with self.assertRaises(ValueError):
            aead.encrypt(b"short", self.nonce, b"x")
        with self.assertRaises(ValueError):
            aead.decrypt(b"short", self.nonce, b"x" * 32)

    def test_bad_nonce_length_rejected(self) -> None:
        with self.assertRaises(ValueError):
            aead.encrypt(self.key, b"short", b"x")
        with self.assertRaises(ValueError):
            aead.decrypt(self.key, b"short", b"x" * 32)


class Argon2idTests(unittest.TestCase):
    def test_deterministic_for_same_inputs(self) -> None:
        salt = os.urandom(kdf.SALT_LEN)
        a = kdf.argon2id(b"correct horse", salt, **_FAST)
        b = kdf.argon2id(b"correct horse", salt, **_FAST)
        self.assertEqual(a, b)
        self.assertEqual(len(a), kdf.ARGON2_DEFAULT_HASH_LEN)

    def test_salt_changes_output(self) -> None:
        a = kdf.argon2id(b"pw", os.urandom(kdf.SALT_LEN), **_FAST)
        b = kdf.argon2id(b"pw", os.urandom(kdf.SALT_LEN), **_FAST)
        self.assertNotEqual(a, b)

    def test_passphrase_changes_output(self) -> None:
        salt = os.urandom(kdf.SALT_LEN)
        a = kdf.argon2id(b"pw-one", salt, **_FAST)
        b = kdf.argon2id(b"pw-two", salt, **_FAST)
        self.assertNotEqual(a, b)

    def test_hash_len_honoured(self) -> None:
        salt = os.urandom(kdf.SALT_LEN)
        out = kdf.argon2id(b"pw", salt, hash_len=64, **_FAST)
        self.assertEqual(len(out), 64)

    def test_short_salt_rejected(self) -> None:
        with self.assertRaises(ValueError):
            kdf.argon2id(b"pw", b"1234567", **_FAST)  # 7 bytes < 8

    def test_non_bytes_passphrase_rejected(self) -> None:
        with self.assertRaises(TypeError):
            kdf.argon2id("not-bytes", os.urandom(kdf.SALT_LEN), **_FAST)  # type: ignore[arg-type]


class HkdfTests(unittest.TestCase):
    def test_deterministic(self) -> None:
        ikm = os.urandom(32)
        a = kdf.hkdf(ikm, salt=b"s", info=b"i", length=32)
        b = kdf.hkdf(ikm, salt=b"s", info=b"i", length=32)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 32)

    def test_info_separates_outputs(self) -> None:
        ikm = os.urandom(32)
        a = kdf.hkdf(ikm, info=b"context-a")
        b = kdf.hkdf(ikm, info=b"context-b")
        self.assertNotEqual(a, b)

    def test_length_honoured(self) -> None:
        self.assertEqual(len(kdf.hkdf(os.urandom(32), length=48)), 48)


class SecureBytesTests(unittest.TestCase):
    def test_write_read_round_trip(self) -> None:
        with SecureBytes(16) as buf:
            buf.write(b"abcdefghijklmnop")
            self.assertEqual(buf.bytes(), b"abcdefghijklmnop")
            self.assertEqual(len(buf), 16)

    def test_write_at_offset(self) -> None:
        with SecureBytes(8) as buf:
            buf.write(b"\x00" * 8)
            buf.write(b"XY", offset=3)
            self.assertEqual(buf.bytes()[3:5], b"XY")

    def test_zero_wipes(self) -> None:
        with SecureBytes(8) as buf:
            buf.write(b"secret!!")
            buf.zero()
            self.assertEqual(buf.bytes(), b"\x00" * 8)

    def test_rejects_zero_size(self) -> None:
        with self.assertRaises(ValueError):
            SecureBytes(0)

    def test_rejects_out_of_bounds_write(self) -> None:
        with SecureBytes(4) as buf:
            with self.assertRaises(ValueError):
                buf.write(b"toolong")
            with self.assertRaises(ValueError):
                buf.write(b"x", offset=-1)

    def test_use_after_free_raises(self) -> None:
        buf = SecureBytes(4)
        buf.write(b"abcd")
        buf.free()
        with self.assertRaises(RuntimeError):
            buf.bytes()
        with self.assertRaises(RuntimeError):
            buf.write(b"x")

    def test_free_is_idempotent(self) -> None:
        buf = SecureBytes(4)
        buf.free()
        buf.free()  # must not raise

    def test_context_manager_frees(self) -> None:
        with SecureBytes(4) as buf:
            buf.write(b"abcd")
        with self.assertRaises(RuntimeError):
            buf.bytes()


class SecureMemStatusTests(unittest.TestCase):
    def test_swap_active_is_bool(self) -> None:
        self.assertIsInstance(swap_active(), bool)

    def test_mlock_status_shape(self) -> None:
        st = mlock_status()
        self.assertIn("mlock_ok", st)
        self.assertIn("swap_active", st)
        self.assertIn("reason", st)
        self.assertIn("platform", st)
        self.assertIsInstance(st["mlock_ok"], bool)


if __name__ == "__main__":
    unittest.main()
