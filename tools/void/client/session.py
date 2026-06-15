"""UI-agnostic VOID session controller.

Everything VOID does between "user picks a room" and "user leaves"
lives here: the Tor/WS transport, the X3DH + Double Ratchet handshakes,
per-peer session state, presence, cover traffic, and RAM purge. None of
it touches Textual.

Two front-ends drive the same controller through the :class:`VoidUI`
callback surface:

* ``tools.void.client.app.VoidApp`` — the standalone Textual app
  (``babel --exec void``), which renders the callbacks onto its screen
  stack.
* ``tools.void.client.chrome_view.VoidView`` — the in-chrome service
  view mounted by the babel suite menu, which renders the callbacks
  into the chrome's content slot.

Keeping the orchestration in one place means the crypto/wire logic is
audited once, and the in-chrome migration (docs/V2_REDESIGN.md §7.5)
adds a second view without forking the protocol code.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Optional, Protocol, runtime_checkable

from . import crypto, ratchet
from .cover import CoverTraffic
from .net import Net
from .sas import sas_words
from .screens.lobby import translate_error


PeerState = str  # "pending" | "ready" | "failed"


class PeerSession:
    """Per-peer ratchet + queue state. Plain class (no dataclass) so the
    mutable list defaults are unambiguous."""

    __slots__ = ("uid", "ik_pub", "bundle", "dr", "state", "trusted",
                 "outbox", "inbound_buffer")

    def __init__(self, uid: str) -> None:
        self.uid = uid
        self.ik_pub: Optional[bytes] = None        # Ed25519 IK pub from bundle
        self.bundle: Optional[object] = None       # ratchet.Bundle after fetch
        self.dr: Optional[ratchet.VoidDoubleRatchet] = None
        self.state: PeerState = "pending"
        self.trusted: bool = False
        self.outbox: list[bytes] = []              # padded PTs queued pre-DR
        self.inbound_buffer: list[dict] = []       # msg frames seen pre-DR


MAX_INBOUND_BUFFER = 16   # cap early-msg buffering to resist memory abuse


@runtime_checkable
class VoidUI(Protocol):
    """Render surface the session pushes events to.

    All methods are synchronous and must not block; the session calls
    them from the event loop. A front-end may ignore any it doesn't
    need (the standalone app and the in-chrome view both implement the
    full set).
    """

    def on_system(self, text: str, *, error: bool = False) -> None: ...
    def on_message(self, ts: datetime, fp: str, text: str, *,
                   is_self: bool, trusted: bool) -> None: ...
    def on_status_changed(self) -> None: ...
    def on_connecting_start(self) -> None: ...
    def on_connecting_step(self, idx: int) -> None: ...
    def on_connecting_failed(self, msg: str) -> None: ...
    def on_enter_chat(self, room_display: str) -> None: ...
    def on_return_to_lobby(self, error: str | None) -> None: ...
    def on_users_changed(self, users: list[str]) -> None: ...
    def on_quit(self) -> None: ...


class VoidSession:
    """Owns one VOID node's transport + crypto state."""

    def __init__(
        self,
        ui: VoidUI,
        *,
        server: str,
        insecure: bool,
        onion_target: str | None,
        clearnet: bool,
        socks_url: str,
        cover_enabled: bool,
    ) -> None:
        self.ui = ui
        self.default_server = server
        self.insecure = insecure
        self.onion_target = onion_target
        self.clearnet = clearnet
        self.socks_url = socks_url
        self.cover_enabled = cover_enabled
        self.expected_fp: str | None = None      # pinned peer fp from invite

        # Per-session state — None/empty outside a room.
        self.net: Net | None = None
        self.identity: ratchet.Identity | None = None
        self.self_uid: str | None = None
        self.room_id: str | None = None
        self.room_display: str | None = None
        self.users: list[str] = []
        self.peer_sessions: dict[str, PeerSession] = {}
        self._intentional_close = False
        self._cover: CoverTraffic | None = None

    # ---------- identity helpers ----------

    def identity_fp_or(self, default: str) -> str:
        return self.identity.fp8 if self.identity else default

    def identity_full_fp_or(self, default: str) -> str:
        return self.identity.fp_full if self.identity else default

    def in_room(self) -> bool:
        return self.net is not None and self.identity is not None

    # ---------- lobby -> chat ----------

    async def enter_room(self, room_key: str, password: str,
                         server_url: str) -> None:
        proxy_url: str | None = None
        url = server_url
        if self.onion_target:
            proxy_url = self.socks_url
            url = f"ws://{self.onion_target}"

        self.ui.on_connecting_start()
        self.ui.on_connecting_step(0)        # reaching tor
        await asyncio.sleep(0.1)

        room_id = crypto.derive_room_id(room_key + "\x00" + password)
        try:
            ident = ratchet.new_identity(num_opks=10)
        except Exception as e:
            msg = f"identity init failed: {type(e).__name__}"
            self.ui.on_connecting_failed(msg)
            await asyncio.sleep(1.2)
            self.ui.on_return_to_lobby(msg)
            return

        self.ui.on_connecting_step(1)        # connecting to .onion
        net = Net(url, insecure=self.insecure, proxy_url=proxy_url)
        try:
            await net.connect()
        except Exception as e:
            friendly = translate_error(f"{type(e).__name__} {e}")
            self.ui.on_connecting_failed(friendly)
            await asyncio.sleep(1.5)
            self.ui.on_return_to_lobby(friendly)
            return

        self.net = net
        self.identity = ident
        self.room_id = room_id
        self.room_display = room_key
        self.peer_sessions = {}
        self.users = []
        self.self_uid = None
        self._intentional_close = False

        net.start_reader(self._on_ws_message, self._on_ws_closed)

        self.ui.on_connecting_step(2)        # publish bundle
        await net.send({
            "type": "publish_bundle",
            "bundle": ratchet.serialise_bundle(ident.state.bundle),
        })
        await net.send({"type": "join", "roomId": room_id})

        self.ui.on_connecting_step(3)        # ratchet handshakes (async)
        await asyncio.sleep(0.4)
        self.ui.on_connecting_step(4)        # ready
        await asyncio.sleep(0.25)

        self.ui.on_enter_chat(room_key)

        if self.cover_enabled:
            self._cover = CoverTraffic(self._send_dummy_message)
            self._cover.start()

    # ---------- send / receive ----------

    async def send_message(self, text: str) -> bool:
        """Returns False if the message was rejected (too long / no session)."""
        if not self.net or not self.identity or not text:
            return False
        pt_bytes = crypto.encode_plaintext_text(text)
        if len(pt_bytes) + 1 > crypto.MAX_PLAINTEXT:
            self.ui.on_system("MESSAGE TOO LONG (max 8 KB)", error=True)
            return False
        padded = crypto.pad_iso7816(pt_bytes, crypto.PAD_BLOCK)
        for peer in list(self.peer_sessions.values()):
            await self._send_to_peer(peer, padded)

        # Echo locally so the user always sees their own message.
        self.ui.on_message(datetime.now(), self.identity.fp8, text,
                           is_self=True, trusted=True)
        if self._cover is not None:
            self._cover.note_real_send()
        return True

    async def _send_dummy_message(self) -> None:
        if not self.net or not self.identity:
            return
        padded = crypto.pad_iso7816(crypto.encode_plaintext_dummy(),
                                    crypto.PAD_BLOCK)
        for peer in list(self.peer_sessions.values()):
            await self._send_to_peer(peer, padded)

    async def _send_to_peer(self, peer: PeerSession, padded: bytes) -> bool:
        if peer.state == "failed":
            return False
        if peer.dr is None:
            peer.outbox.append(padded)
            if peer.bundle is None:
                await self._request_bundle(peer.uid)
            else:
                await self._initiate_handshake(peer)
            return False
        try:
            em = await ratchet.ratchet_encrypt(
                peer.dr, self.identity.ik_pub, peer.ik_pub, padded)
        except Exception:
            return False
        await self._send_msg_frame(peer, em)
        return True

    async def _send_msg_frame(self, peer: PeerSession,
                              em: ratchet.EncryptedMessage) -> None:
        dr_ser = ratchet.serialise_dr_message(em)
        sig_payload = em.header.ratchet_pub + em.ciphertext
        sig = ratchet.sign_with_identity(self.identity, sig_payload)
        await self.net.send({
            "type": "msg",
            "roomId": self.room_id,
            "to": peer.uid,
            "dr": dr_ser,
            "sig": crypto.b64e(sig),
        })

    async def _initiate_handshake(self, peer: PeerSession) -> None:
        if peer.bundle is None or self.identity is None:
            return
        if peer.dr is not None:
            return
        hello = crypto.pad_iso7816(crypto.encode_plaintext_hello(),
                                   crypto.PAD_BLOCK)
        try:
            dr, x3dh_h, em = await ratchet.handshake_active(
                self.identity, peer.bundle, hello)
        except Exception:
            peer.state = "failed"
            self.ui.on_status_changed()
            return
        peer.dr = dr
        peer.ik_pub = peer.bundle.identity_key
        peer.state = "ready"
        x3dh_ser = ratchet.serialise_x3dh_header(x3dh_h)
        dr_ser = ratchet.serialise_dr_message(em)
        sig_payload = em.header.ratchet_pub + em.ciphertext
        sig = ratchet.sign_with_identity(self.identity, sig_payload)
        await self.net.send({
            "type": "ratchet_init",
            "to": peer.uid,
            "x3dh": x3dh_ser,
            "dr": dr_ser,
            "sig": crypto.b64e(sig),
        })
        outbox, peer.outbox = peer.outbox, []
        for padded in outbox:
            try:
                em2 = await ratchet.ratchet_encrypt(
                    peer.dr, self.identity.ik_pub, peer.ik_pub, padded)
                await self._send_msg_frame(peer, em2)
            except Exception:
                pass
        self.ui.on_status_changed()

    async def _request_bundle(self, target_uid: str) -> None:
        if self.net is None:
            return
        await self.net.send({"type": "fetch_bundle", "target": target_uid})

    async def leave_room(self) -> None:
        await self.purge(send_leave=True)
        self.ui.on_return_to_lobby(None)

    # ---------- ws handlers ----------

    async def _on_ws_message(self, data: dict) -> None:
        t = data.get("type")
        if t == "presence":
            await self._on_presence(data)
        elif t == "bundle":
            await self._on_bundle(data)
        elif t == "ratchet_init":
            await self._on_ratchet_init(data)
        elif t == "msg":
            await self._on_msg(data)

    async def _on_presence(self, data: dict) -> None:
        users = data.get("users") or []
        if not isinstance(users, list):
            return
        users = [u for u in users if isinstance(u, str)]
        self.users = users

        present_set = set(users)
        for uid in users:
            if uid in self.peer_sessions:
                continue
            self.peer_sessions[uid] = PeerSession(uid=uid)
            await self._request_bundle(uid)

        for uid in list(self.peer_sessions.keys()):
            if uid not in present_set:
                self.peer_sessions.pop(uid, None)

        self.ui.on_users_changed(self.users)
        self.ui.on_status_changed()

    async def _on_bundle(self, data: dict) -> None:
        target = data.get("target")
        if not isinstance(target, str):
            return
        if data.get("missing"):
            peer = self.peer_sessions.get(target)
            if peer:
                peer.state = "failed"
                self.ui.on_status_changed()
            return
        bundle_json = data.get("bundle")
        if not isinstance(bundle_json, dict):
            return
        try:
            bundle = ratchet.deserialise_bundle(bundle_json)
        except Exception:
            return

        # Detect that this bundle is ours by comparing IK pub.
        if self.identity is not None and bundle.identity_key == self.identity.ik_pub:
            self.self_uid = target
            self.peer_sessions.pop(target, None)
            self.ui.on_status_changed()
            return

        peer = self.peer_sessions.get(target)
        if peer is None:
            peer = PeerSession(uid=target)
            self.peer_sessions[target] = peer
        peer.bundle = bundle
        peer.ik_pub = bundle.identity_key

        # Initiation rule: lower uid initiates. If we don't know our uid
        # yet, proactively initiate (worst case: race, resolved on receipt).
        if self.self_uid is None or self.self_uid < target:
            if peer.dr is None:
                await self._initiate_handshake(peer)
        self.ui.on_status_changed()

    async def _on_ratchet_init(self, data: dict) -> None:
        if self.identity is None:
            return
        from_uid = data.get("from")
        if not isinstance(from_uid, str):
            return
        x3dh_ser = data.get("x3dh")
        dr_ser = data.get("dr")
        if not isinstance(x3dh_ser, dict) or not isinstance(dr_ser, dict):
            return
        try:
            x3dh_h = ratchet.deserialise_x3dh_header(x3dh_ser)
            em = ratchet.deserialise_dr_message(dr_ser)
        except Exception:
            return
        sig_b = data.get("sig")
        if not isinstance(sig_b, str):
            return
        try:
            sig = crypto.b64d(sig_b)
        except Exception:
            return
        sender_ik = x3dh_h.identity_key
        sig_payload = em.header.ratchet_pub + em.ciphertext
        if not ratchet.verify_blob(sender_ik, sig, sig_payload):
            return

        # Enforce expected_fp pinning from an invite link, if present.
        if self.expected_fp:
            actual_fp = crypto.fingerprint8(sender_ik)
            if actual_fp != self.expected_fp:
                self.ui.on_system(
                    f"rejected handshake from <{actual_fp}> "
                    f"(invite pinned <{self.expected_fp}>)", error=True)
                return

        peer = self.peer_sessions.get(from_uid)
        if peer is None:
            peer = PeerSession(uid=from_uid)
            self.peer_sessions[from_uid] = peer

        # Tiebreaker: if we already have a DR and our uid < theirs, keep ours.
        if peer.dr is not None and self.self_uid is not None and self.self_uid < from_uid:
            return

        try:
            dr, plaintext = await ratchet.handshake_passive(
                self.identity, x3dh_h, em)
        except Exception:
            peer.state = "failed"
            self.ui.on_status_changed()
            return
        peer.dr = dr
        peer.ik_pub = sender_ik
        peer.state = "ready"

        pt_unpadded = crypto.unpad_iso7816(plaintext)
        if pt_unpadded is not None:
            obj = crypto.decode_plaintext(pt_unpadded)
            if obj and not obj.get("hello") and not obj.get("dummy"):
                text = obj.get("text")
                if isinstance(text, str):
                    self.ui.on_message(
                        datetime.now(), crypto.fingerprint8(sender_ik),
                        text, is_self=False, trusted=peer.trusted)
        outbox, peer.outbox = peer.outbox, []
        for padded in outbox:
            try:
                em2 = await ratchet.ratchet_encrypt(
                    peer.dr, self.identity.ik_pub, peer.ik_pub, padded)
                await self._send_msg_frame(peer, em2)
            except Exception:
                pass
        buffered, peer.inbound_buffer = peer.inbound_buffer, []
        for buffered_frame in buffered:
            await self._on_msg(buffered_frame)
        self.ui.on_status_changed()

    async def _on_msg(self, data: dict) -> None:
        if self.identity is None:
            return
        from_uid = data.get("from")
        if not isinstance(from_uid, str):
            return
        peer = self.peer_sessions.get(from_uid)
        if peer is None:
            peer = PeerSession(uid=from_uid)
            self.peer_sessions[from_uid] = peer
        if peer.dr is None or peer.ik_pub is None:
            if len(peer.inbound_buffer) < MAX_INBOUND_BUFFER:
                peer.inbound_buffer.append(data)
            return
        dr_ser = data.get("dr")
        sig_b = data.get("sig")
        if not isinstance(dr_ser, dict) or not isinstance(sig_b, str):
            return
        try:
            em = ratchet.deserialise_dr_message(dr_ser)
            sig = crypto.b64d(sig_b)
        except Exception:
            return
        sig_payload = em.header.ratchet_pub + em.ciphertext
        if not ratchet.verify_blob(peer.ik_pub, sig, sig_payload):
            return
        try:
            plaintext = await ratchet.ratchet_decrypt(
                peer.dr, peer.ik_pub, self.identity.ik_pub, em)
        except Exception:
            return
        pt_unpadded = crypto.unpad_iso7816(plaintext)
        if pt_unpadded is None:
            return
        obj = crypto.decode_plaintext(pt_unpadded)
        if not obj or obj.get("hello") or obj.get("dummy"):
            return
        text = obj.get("text")
        if not isinstance(text, str):
            return
        self.ui.on_message(
            datetime.now(), crypto.fingerprint8(peer.ik_pub),
            text, is_self=False, trusted=peer.trusted)

    async def _on_ws_closed(self, reason: str) -> None:
        if self._intentional_close:
            return
        await self.purge(send_leave=False)
        self.ui.on_return_to_lobby(f"// disconnected ({reason})")

    # ---------- peers / SAS ----------

    def list_peers(self) -> list[dict]:
        if not self.identity:
            return []
        out = []
        for _uid, p in sorted(self.peer_sessions.items()):
            if p.ik_pub is None:
                continue
            out.append({
                "fp": crypto.fingerprint8(p.ik_pub),
                "trusted": p.trusted,
                "sas": sas_words(self.identity.ik_pub, p.ik_pub),
            })
        return out

    def _find_peer_by_fp8(self, fp8: str) -> PeerSession | None:
        for p in self.peer_sessions.values():
            if p.ik_pub is not None and crypto.fingerprint8(p.ik_pub) == fp8:
                return p
        return None

    def peer_sas(self, fp8: str) -> dict | None:
        if not self.identity:
            return None
        p = self._find_peer_by_fp8(fp8)
        if p is None or p.ik_pub is None:
            return None
        return {"fp": fp8, "sas": sas_words(self.identity.ik_pub, p.ik_pub)}

    def mark_trusted(self, fp8: str) -> bool:
        p = self._find_peer_by_fp8(fp8)
        if p is None:
            return False
        p.trusted = True
        return True

    def ratchet_status(self) -> str:
        """'green' / 'yellow' / 'red' based on peer DR readiness."""
        if not self.peer_sessions:
            return "green"
        if any(p.state == "failed" for p in self.peer_sessions.values()):
            return "red"
        if any(p.dr is None and p.state != "failed"
               for p in self.peer_sessions.values()):
            return "yellow"
        return "green"

    # ---------- purge ----------

    async def purge(self, send_leave: bool) -> None:
        self._intentional_close = True
        if self._cover is not None:
            try:
                await self._cover.stop()
            except Exception:
                pass
            self._cover = None
        if self.net:
            if send_leave and self.room_id:
                try:
                    await asyncio.wait_for(
                        self.net.send({"type": "leave",
                                       "roomId": self.room_id}),
                        timeout=1.0,
                    )
                except Exception:
                    pass
            try:
                await self.net.close()
            except Exception:
                pass
        self.net = None
        if self.identity is not None:
            self.identity.destroy()
        self.identity = None
        self.peer_sessions = {}
        self.room_id = None
        self.room_display = None
        self.users = []
        self.self_uid = None

    async def quit(self) -> None:
        await self.purge(send_leave=True)
        self.ui.on_quit()


__all__ = ["VoidSession", "VoidUI", "PeerSession", "MAX_INBOUND_BUFFER"]
