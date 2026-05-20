"""Cross-tool in-memory artifact storage.

See docs/V2_REDESIGN.md §4.4. The vault is owned by the suite app
(``babel.shell.ChromeApp``) and holds artifacts produced by one tool
that another tool may consume — e.g., a MASK-generated identity is
stored as IDENTITY and becomes selectable in VOID's lobby; a CARRIER
capsule is stored so a follow-up `extract` can address it by
fingerprint instead of re-typing a path.

Properties:

* **In-memory only.** Never touches disk. Cleared on app quit. If
  the user wants to keep an artifact across runs, each tool exposes
  its own ``[X] export`` flow (passphrase-encrypted on the way out).
* **Zeroized on drop / purge.** Payloads live in
  ``shared.crypto.secure_mem.SecureBytes`` buffers so they are
  mlock'd where the platform allows and overwritten with zeros when
  the artifact is removed.
* **Thread-safe.** Textual is single-threaded but services may post
  artifacts from worker tasks; an ``RLock`` keeps the dict consistent.
* **Soft expiry.** Artifacts with ``expires_at`` are dropped on the
  next read (lazy sweep — no background timer to leak).

The vault is intentionally dumb storage: each tool owns its own
serializer. ``payload`` is just opaque bytes from the vault's
perspective.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from threading import RLock
from typing import Iterator

from shared.crypto.secure_mem import SecureBytes


class ArtifactKind(StrEnum):
    """The kinds of cross-tool state currently recognised.

    Add new kinds only when a real consumer exists — every kind is
    contract surface between two tools.
    """

    IDENTITY = "identity"   # MASK output, consumed by VOID / CARRIER
    CAPSULE  = "capsule"    # CARRIER stego container metadata
    INVITE   = "invite"     # VOID void:// link, shared across screens


@dataclass(slots=True)
class Artifact:
    """One stored item.

    Do NOT construct directly. Call :meth:`Vault.put` which wraps the
    raw bytes into a SecureBytes-backed buffer for you. Reading
    :attr:`payload_bytes` returns a fresh ``bytes`` copy each time;
    the caller is responsible for not retaining it longer than needed.
    """

    kind: ArtifactKind
    label: str
    fingerprint: str
    created_at: float
    expires_at: float | None
    _buf: SecureBytes

    @property
    def size(self) -> int:
        return self._buf._size  # type: ignore[attr-defined]

    def payload_bytes(self) -> bytes:
        return self._buf.bytes()

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now if now is not None else time.time())


class Vault:
    """In-memory artifact store keyed by fingerprint."""

    def __init__(self) -> None:
        self._items: dict[str, Artifact] = {}
        self._lock = RLock()

    # ---- mutation ----------------------------------------------------------

    def put(
        self,
        kind: ArtifactKind,
        label: str,
        fingerprint: str,
        payload: bytes,
        expires_at: float | None = None,
    ) -> Artifact:
        """Store ``payload`` as a new Artifact and return it.

        Re-putting the same fingerprint replaces the previous entry
        and zeroizes its buffer. Empty fingerprints are rejected to
        prevent accidental collisions on the empty string key.
        """
        if not fingerprint:
            raise ValueError("fingerprint cannot be empty")
        if not payload:
            raise ValueError("payload cannot be empty")
        buf = SecureBytes(len(payload))
        buf.write(payload)
        artifact = Artifact(
            kind=kind,
            label=label,
            fingerprint=fingerprint,
            created_at=time.time(),
            expires_at=expires_at,
            _buf=buf,
        )
        with self._lock:
            previous = self._items.get(fingerprint)
            self._items[fingerprint] = artifact
        if previous is not None:
            previous._buf.free()
        return artifact

    def drop(self, fingerprint: str) -> bool:
        """Remove ``fingerprint`` and zeroize its buffer.

        Returns True if something was removed.
        """
        with self._lock:
            artifact = self._items.pop(fingerprint, None)
        if artifact is None:
            return False
        artifact._buf.free()
        return True

    def purge_all(self) -> None:
        """Zeroize every payload and clear the vault.

        Called by ``ChromeApp.action_purge_quit`` on suite exit.
        """
        with self._lock:
            items = list(self._items.values())
            self._items.clear()
        for artifact in items:
            artifact._buf.free()

    # ---- inspection --------------------------------------------------------

    def list(self, kind: ArtifactKind | None = None) -> list[Artifact]:
        """All artifacts, optionally filtered by ``kind``.

        Expired entries are dropped before returning. Order is
        insertion order (dict ordering), so the UI can show "most
        recent at the bottom" without bookkeeping.
        """
        with self._lock:
            self._sweep_expired_locked()
            items = list(self._items.values())
        if kind is None:
            return items
        return [a for a in items if a.kind == kind]

    def get(self, fingerprint: str) -> Artifact | None:
        with self._lock:
            self._sweep_expired_locked()
            return self._items.get(fingerprint)

    def __len__(self) -> int:
        with self._lock:
            self._sweep_expired_locked()
            return len(self._items)

    def __iter__(self) -> Iterator[Artifact]:
        return iter(self.list())

    def __contains__(self, fingerprint: object) -> bool:
        if not isinstance(fingerprint, str):
            return False
        return self.get(fingerprint) is not None

    # ---- internals ---------------------------------------------------------

    def _sweep_expired_locked(self) -> None:
        now = time.time()
        expired = [
            fp for fp, art in self._items.items()
            if art.expires_at is not None and art.expires_at <= now
        ]
        for fp in expired:
            self._items.pop(fp)._buf.free()


__all__ = ["Vault", "Artifact", "ArtifactKind"]
