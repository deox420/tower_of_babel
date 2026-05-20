"""Tests for babel.vault.

Stdlib ``unittest`` only — the repo doesn't ship pytest. Run with::

    python -m unittest tests.test_vault -v
"""
from __future__ import annotations

import time
import unittest

from babel.vault import Artifact, ArtifactKind, Vault


class VaultBasicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.v = Vault()

    def tearDown(self) -> None:
        self.v.purge_all()

    def test_starts_empty(self) -> None:
        self.assertEqual(len(self.v), 0)
        self.assertEqual(self.v.list(), [])
        self.assertIsNone(self.v.get("nope"))
        self.assertNotIn("nope", self.v)

    def test_put_returns_artifact(self) -> None:
        art = self.v.put(
            ArtifactKind.IDENTITY, "alpine-hiker", "F7Z2JK9P", b"id-bytes"
        )
        self.assertIsInstance(art, Artifact)
        self.assertEqual(art.kind, ArtifactKind.IDENTITY)
        self.assertEqual(art.label, "alpine-hiker")
        self.assertEqual(art.fingerprint, "F7Z2JK9P")
        self.assertEqual(art.payload_bytes(), b"id-bytes")
        self.assertGreater(art.created_at, 0)
        self.assertIsNone(art.expires_at)

    def test_get_after_put(self) -> None:
        self.v.put(ArtifactKind.IDENTITY, "a", "fp-1", b"x")
        got = self.v.get("fp-1")
        self.assertIsNotNone(got)
        self.assertEqual(got.payload_bytes(), b"x")
        self.assertIn("fp-1", self.v)

    def test_drop(self) -> None:
        self.v.put(ArtifactKind.IDENTITY, "a", "fp-1", b"x")
        self.assertTrue(self.v.drop("fp-1"))
        self.assertFalse(self.v.drop("fp-1"))  # idempotent on second call
        self.assertIsNone(self.v.get("fp-1"))

    def test_put_rejects_empty_fingerprint(self) -> None:
        with self.assertRaises(ValueError):
            self.v.put(ArtifactKind.IDENTITY, "a", "", b"x")

    def test_put_rejects_empty_payload(self) -> None:
        # Empty bytes wouldn't be storable anyway (SecureBytes refuses
        # size 0); reject explicitly for a clear error message.
        with self.assertRaises(ValueError):
            self.v.put(ArtifactKind.IDENTITY, "a", "fp", b"")


class VaultFilteringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.v = Vault()
        self.v.put(ArtifactKind.IDENTITY, "alpine-hiker", "id-1", b"a")
        self.v.put(ArtifactKind.IDENTITY, "silver-fox",   "id-2", b"b")
        self.v.put(ArtifactKind.INVITE,   "ar3-xelf3a",   "iv-1", b"c")

    def tearDown(self) -> None:
        self.v.purge_all()

    def test_list_all(self) -> None:
        self.assertEqual(len(self.v.list()), 3)

    def test_list_by_kind(self) -> None:
        ids = self.v.list(kind=ArtifactKind.IDENTITY)
        self.assertEqual(len(ids), 2)
        self.assertEqual({a.label for a in ids},
                         {"alpine-hiker", "silver-fox"})

    def test_list_kind_with_no_matches(self) -> None:
        self.assertEqual(self.v.list(kind=ArtifactKind.CAPSULE), [])

    def test_iteration(self) -> None:
        labels = {a.label for a in self.v}
        self.assertEqual(
            labels, {"alpine-hiker", "silver-fox", "ar3-xelf3a"}
        )


class VaultReplacementTests(unittest.TestCase):
    def test_same_fingerprint_replaces(self) -> None:
        v = Vault()
        try:
            v.put(ArtifactKind.IDENTITY, "old-label", "fp", b"old")
            v.put(ArtifactKind.IDENTITY, "new-label", "fp", b"new")
            self.assertEqual(len(v), 1)
            self.assertEqual(v.get("fp").label, "new-label")
            self.assertEqual(v.get("fp").payload_bytes(), b"new")
        finally:
            v.purge_all()


class VaultExpiryTests(unittest.TestCase):
    def test_past_expiry_swept_on_list(self) -> None:
        v = Vault()
        try:
            v.put(ArtifactKind.INVITE, "stale", "iv-1", b"x",
                  expires_at=time.time() - 1.0)
            self.assertEqual(v.list(), [])
            self.assertIsNone(v.get("iv-1"))
            self.assertEqual(len(v), 0)
        finally:
            v.purge_all()

    def test_future_expiry_kept(self) -> None:
        v = Vault()
        try:
            v.put(ArtifactKind.INVITE, "live", "iv-1", b"x",
                  expires_at=time.time() + 60.0)
            self.assertEqual(len(v.list()), 1)
            self.assertIsNotNone(v.get("iv-1"))
        finally:
            v.purge_all()

    def test_is_expired_predicate(self) -> None:
        v = Vault()
        try:
            past = v.put(ArtifactKind.INVITE, "a", "iv-1", b"x",
                         expires_at=time.time() - 1.0)
            self.assertTrue(past.is_expired())
            future = v.put(ArtifactKind.INVITE, "b", "iv-2", b"y",
                           expires_at=time.time() + 60.0)
            self.assertFalse(future.is_expired())
            never = v.put(ArtifactKind.INVITE, "c", "iv-3", b"z")
            self.assertFalse(never.is_expired())
        finally:
            v.purge_all()


class VaultPurgeTests(unittest.TestCase):
    def test_purge_all_clears_everything(self) -> None:
        v = Vault()
        for i in range(5):
            v.put(ArtifactKind.IDENTITY, f"id-{i}", f"fp-{i}", b"x")
        self.assertEqual(len(v), 5)
        v.purge_all()
        self.assertEqual(len(v), 0)
        self.assertEqual(v.list(), [])

    def test_purge_all_idempotent(self) -> None:
        v = Vault()
        v.put(ArtifactKind.IDENTITY, "a", "fp", b"x")
        v.purge_all()
        v.purge_all()  # second call must not blow up
        self.assertEqual(len(v), 0)


class VaultChromeAppIntegrationTests(unittest.TestCase):
    """ChromeApp wires a Vault by default — verify construction."""

    def test_chrome_app_has_vault(self) -> None:
        from babel.shell import ChromeApp

        app = ChromeApp()
        self.assertIsInstance(app.vault, Vault)
        self.assertEqual(len(app.vault), 0)

    def test_chrome_app_accepts_injected_vault(self) -> None:
        from babel.shell import ChromeApp

        vault = Vault()
        vault.put(ArtifactKind.IDENTITY, "pre-seeded", "fp", b"x")
        try:
            app = ChromeApp(vault=vault)
            self.assertIs(app.vault, vault)
            self.assertEqual(len(app.vault), 1)
        finally:
            vault.purge_all()


if __name__ == "__main__":
    unittest.main()
