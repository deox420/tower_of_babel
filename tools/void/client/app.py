"""VOID client v3 — X3DH + Double Ratchet on top of Tor + padding + cover."""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from textual.app import App

from . import crypto, ratchet
from .cover import CoverTraffic
from .net import Net
from .sas import sas_words
from .screens.chat import ChatScreen
from .screens.connecting import ConnectingScreen
from .screens.lobby import LobbyScreen, translate_error
from .screens.starmap import StarMapScreen


PeerState = str  # "pending" | "ready" | "failed"


@dataclass
class PeerSession:
    uid: str
    ik_pub: Optional[bytes] = None          # Ed25519 IK pub from bundle
    bundle: Optional["object"] = None       # ratchet.Bundle, set after fetch
    dr: Optional[ratchet.VoidDoubleRatchet] = None
    state: PeerState = "pending"
    trusted: bool = False
    outbox: list[bytes] = field(default_factory=list)   # padded plaintexts queued before DR ready
    inbound_buffer: list[dict] = field(default_factory=list)  # raw msg frames received before our DR exists


MAX_INBOUND_BUFFER = 16   # drop further early-msg frames after this many to avoid memory abuse


class VoidApp(App):
    CSS_PATH = "style.tcss"
    TITLE = "VOID"
    SUB_TITLE = "ephemeral node"

    BINDINGS = []

    def __init__(
        self,
        server: str,
        insecure: bool,
        onion_target: str | None,
        clearnet: bool,
        socks_url: str,
        cover_enabled: bool,
    ) -> None:
        super().__init__()
        self.default_server = server
        self.insecure = insecure
        self.onion_target = onion_target
        self.clearnet = clearnet
        self.socks_url = socks_url
        self.cover_enabled = cover_enabled
        self._initial_lobby_err: str | None = None

        # Per-session state — None outside a room.
        self.net: Net | None = None
        self.identity: ratchet.Identity | None = None
        self.self_uid: str | None = None
        self.room_id: str | None = None
        self.room_display: str | None = None
        self.users: list[str] = []
        self.peer_sessions: dict[str, PeerSession] = {}   # uid -> PeerSession
        self.chat_screen: ChatScreen | None = None
        self.starmap_screen: StarMapScreen | None = None
        self._intentional_close = False
        self._cover: CoverTraffic | None = None
        self.compact: bool = False
        self.expected_fp: str | None = None     # pinned peer fp from an invite link

    # ---------- lifecycle ----------

    def on_mount(self) -> None:
        self.push_screen(LobbyScreen(self.default_server, self._initial_lobby_err))
        self._initial_lobby_err = None

    def identity_fp_or(self, default: str) -> str:
        return self.identity.fp8 if self.identity else default

    def identity_full_fp_or(self, default: str) -> str:
        return self.identity.fp_full if self.identity else default

    # ---------- lobby -> chat ----------

    async def enter_room(self, room_key: str, password: str, server_url: str) -> None:
        proxy_url: str | None = None
        url = server_url
        if self.onion_target:
            proxy_url = self.socks_url
            url = f"ws://{self.onion_target}"

        # Push the progress screen so the user has visual feedback.
        connecting = ConnectingScreen()
        await self.push_screen(connecting)
        # step 0: reaching tor
        connecting.set_step(0)
        await asyncio.sleep(0.1)

        room_id = crypto.derive_room_id(room_key + "\x00" + password)
        try:
            ident = ratchet.new_identity(num_opks=10)
        except Exception as e:
            connecting.set_failed(f"identity init failed: {type(e).__name__}")
            await asyncio.sleep(1.2)
            self.pop_screen()
            self._return_to_lobby(f"identity init failed: {type(e).__name__}")
            return

        # step 1: connecting to .onion
        connecting.set_step(1)
        net = Net(url, insecure=self.insecure, proxy_url=proxy_url)
        try:
            await net.connect()
        except Exception as e:
            friendly = translate_error(f"{type(e).__name__} {e}")
            connecting.set_failed(friendly)
            await asyncio.sleep(1.5)
            try:
                self.pop_screen()
            except Exception:
                pass
            self._return_to_lobby(friendly)
            return

        self.net = net
        self.identity = ident
        self.room_id = room_id
        self.room_display = room_key
        self.peer_sessions = {}
        self.users = []
        self._intentional_close = False

        net.start_reader(self._on_ws_message, self._on_ws_closed)

        # step 2: publish bundle
        connecting.set_step(2)
        await net.send({
            "type": "publish_bundle",
            "bundle": ratchet.serialise_bundle(ident.state.bundle),
        })
        await net.send({"type": "join", "roomId": room_id})

        # step 3: ratchet handshakes will run async as peers fetch our bundle.
        connecting.set_step(3)
        await asyncio.sleep(0.4)

        # step 4: ready
        connecting.set_step(4)
        await asyncio.sleep(0.25)

        chat = ChatScreen(room_key_display=room_key)
        self.chat_screen = chat
        try:
            self.pop_screen()        # drop ConnectingScreen
        except Exception:
            pass
        await self.push_screen(chat)
        chat.refresh_header()
        chat.refresh_status()

        if self.cover_enabled:
            self._cover = CoverTraffic(self._send_dummy_message)
            self._cover.start()

    # ---------- send / receive ----------

    async def send_message(self, text: str) -> None:
        if not self.net or not self.identity:
            return
        if not text:
            return
        pt_bytes = crypto.encode_plaintext_text(text)
        if len(pt_bytes) + 1 > crypto.MAX_PLAINTEXT:
            if self.chat_screen:
                self.chat_screen.append_system("MESSAGE TOO LONG (max 8 KB)", error=True)
            return
        padded = crypto.pad_iso7816(pt_bytes, crypto.PAD_BLOCK)
        delivered_to_any = False
        for peer in list(self.peer_sessions.values()):
            ok = await self._send_to_peer(peer, padded)
            delivered_to_any = delivered_to_any or ok

        # Echo locally so the user always sees their own message.
        if self.chat_screen:
            self.chat_screen.append_message(
                datetime.now(), self.identity.fp8, text, is_self=True, trusted=True
            )
        if self._cover is not None:
            self._cover.note_real_send()
        # Note: it's fine if no peers are present yet. Message is "into the void".

    async def _send_dummy_message(self) -> None:
        if not self.net or not self.identity:
            return
        padded = crypto.pad_iso7816(crypto.encode_plaintext_dummy(), crypto.PAD_BLOCK)
        for peer in list(self.peer_sessions.values()):
            await self._send_to_peer(peer, padded)

    async def _send_to_peer(self, peer: PeerSession, padded: bytes) -> bool:
        """Encrypt + send one padded plaintext to one peer. Returns True if dispatched."""
        if peer.state == "failed":
            return False
        if peer.dr is None:
            # No DR yet → try to initiate if we have a bundle.
            peer.outbox.append(padded)
            if peer.bundle is None:
                # Need to fetch first.
                await self._request_bundle(peer.uid)
            else:
                await self._initiate_handshake(peer)
            return False
        # Established DR — normal msg.
        try:
            em = await ratchet.ratchet_encrypt(peer.dr, self.identity.ik_pub, peer.ik_pub, padded)
        except Exception:
            return False
        await self._send_msg_frame(peer, em)
        return True

    async def _send_msg_frame(self, peer: PeerSession, em: ratchet.EncryptedMessage) -> None:
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
        """Active X3DH + DR.encrypt_initial_message; sends ratchet_init."""
        if peer.bundle is None or self.identity is None:
            return
        if peer.dr is not None:
            return
        # First initial message is the "hello" payload (always padded).
        hello = crypto.pad_iso7816(crypto.encode_plaintext_hello(), crypto.PAD_BLOCK)
        try:
            dr, x3dh_h, em = await ratchet.handshake_active(self.identity, peer.bundle, hello)
        except Exception as e:
            peer.state = "failed"
            self._refresh_status()
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
        # Drain any queued outbox to this peer with normal msg frames.
        outbox, peer.outbox = peer.outbox, []
        for padded in outbox:
            try:
                em2 = await ratchet.ratchet_encrypt(peer.dr, self.identity.ik_pub, peer.ik_pub, padded)
                await self._send_msg_frame(peer, em2)
            except Exception:
                pass
        self._refresh_status()

    async def _request_bundle(self, target_uid: str) -> None:
        if self.net is None:
            return
        await self.net.send({"type": "fetch_bundle", "target": target_uid})

    async def leave_room(self) -> None:
        await self._purge(send_leave=True)
        while len(self.screen_stack) > 1:
            self.pop_screen()

    async def open_map(self) -> None:
        if self.starmap_screen is None:
            self.starmap_screen = StarMapScreen()
        await self.push_screen(self.starmap_screen)
        self.starmap_screen.update_users(self.users)

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

        # Identify self uid the first time we see ourselves announced.
        # The server hasn't told us our uid directly; we infer it as the
        # only one freshly added when we ourselves just published.
        # Instead, we let self.self_uid be assigned by the first presence
        # update *after* we published — pick the new uid not in our peer
        # set as ours, but only if it's our own (we can detect by trying
        # to send to ourselves... too clumsy). Simpler: leave self.self_uid
        # as None and never put ourselves in peer_sessions; for routing
        # decisions, compare other peers' uids to self.self_uid which we
        # set from the *first* presence frame's new entries by elimination.
        # Cleanest: server doesn't tell us our uid. We avoid needing it by
        # not adding any uid to peer_sessions if it equals our own (we can
        # tell because the corresponding bundle's IK == our IK). When
        # processing presence we just skip our own uid using the bundle-IK
        # match later.

        present_set = set(users)
        for uid in users:
            if uid in self.peer_sessions:
                continue
            # Don't create a session for ourselves. We don't yet know our
            # own uid; we'll discover it the first time the server sends
            # us a bundle for our own uid (we skip those) or by elimination.
            self.peer_sessions[uid] = PeerSession(uid=uid)
            await self._request_bundle(uid)

        # Remove sessions for peers that left.
        for uid in list(self.peer_sessions.keys()):
            if uid not in present_set:
                self.peer_sessions.pop(uid, None)

        if self.starmap_screen and self.starmap_screen.is_mounted:
            self.starmap_screen.update_users(self.users)
        self._refresh_status()

    async def _on_bundle(self, data: dict) -> None:
        target = data.get("target")
        if not isinstance(target, str):
            return
        if data.get("missing"):
            peer = self.peer_sessions.get(target)
            if peer:
                peer.state = "failed"
                self._refresh_status()
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
            self._refresh_status()
            return

        peer = self.peer_sessions.get(target)
        if peer is None:
            peer = PeerSession(uid=target)
            self.peer_sessions[target] = peer
        peer.bundle = bundle
        peer.ik_pub = bundle.identity_key

        # Initiation rule: lower uid initiates. If we don't know our uid
        # yet, we proactively initiate (worst case: race, resolved on
        # ratchet_init receipt).
        if self.self_uid is None or self.self_uid < target:
            if peer.dr is None and peer.outbox:
                await self._initiate_handshake(peer)
            elif peer.dr is None:
                # No queued msg; still initiate so peer can talk to us
                # without waiting. The hello payload is silent.
                await self._initiate_handshake(peer)
        self._refresh_status()

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
        # Verify signature over (target uid || ratchet_pub || ciphertext)
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

        # Fix #1: enforce expected_fp pinning from invite link, if present.
        if self.expected_fp:
            actual_fp = crypto.fingerprint8(sender_ik)
            if actual_fp != self.expected_fp:
                # Someone other than the invited peer is trying to handshake.
                # Refuse silently to avoid leaking that we expected a specific fp.
                if self.chat_screen is not None and self.chat_screen.is_mounted:
                    self.chat_screen.append_system(
                        f"rejected handshake from <{actual_fp}> "
                        f"(invite pinned <{self.expected_fp}>)", error=True
                    )
                return

        peer = self.peer_sessions.get(from_uid)
        if peer is None:
            peer = PeerSession(uid=from_uid)
            self.peer_sessions[from_uid] = peer

        # Tiebreaker: if we already have a DR and our uid < theirs, keep ours.
        if peer.dr is not None and self.self_uid is not None and self.self_uid < from_uid:
            return

        try:
            dr, plaintext = await ratchet.handshake_passive(self.identity, x3dh_h, em)
        except Exception:
            peer.state = "failed"
            self._refresh_status()
            return
        peer.dr = dr
        peer.ik_pub = sender_ik
        peer.state = "ready"

        # Process the initial plaintext (usually "hello"; drop without rendering).
        pt_unpadded = crypto.unpad_iso7816(plaintext)
        if pt_unpadded is not None:
            obj = crypto.decode_plaintext(pt_unpadded)
            if obj and not obj.get("hello") and not obj.get("dummy"):
                text = obj.get("text")
                if isinstance(text, str) and self.chat_screen:
                    self.chat_screen.append_message(
                        datetime.now(),
                        crypto.fingerprint8(sender_ik),
                        text,
                        is_self=False,
                        trusted=peer.trusted,
                    )
        # Drain outbox now that we can send to them.
        outbox, peer.outbox = peer.outbox, []
        for padded in outbox:
            try:
                em2 = await ratchet.ratchet_encrypt(peer.dr, self.identity.ik_pub, peer.ik_pub, padded)
                await self._send_msg_frame(peer, em2)
            except Exception:
                pass
        # Fix #3: drain any msg frames buffered before we had a DR for this peer.
        buffered, peer.inbound_buffer = peer.inbound_buffer, []
        for buffered_frame in buffered:
            await self._on_msg(buffered_frame)
        self._refresh_status()

    async def _on_msg(self, data: dict) -> None:
        if self.identity is None or self.chat_screen is None:
            return
        from_uid = data.get("from")
        if not isinstance(from_uid, str):
            return
        peer = self.peer_sessions.get(from_uid)
        # Fix #3: if the msg arrives before the ratchet_init (server jitter races
        # the two frames), buffer it instead of dropping. Drain on handshake_passive.
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
            plaintext = await ratchet.ratchet_decrypt(peer.dr, peer.ik_pub, self.identity.ik_pub, em)
        except Exception:
            return
        pt_unpadded = crypto.unpad_iso7816(plaintext)
        if pt_unpadded is None:
            return
        obj = crypto.decode_plaintext(pt_unpadded)
        if not obj:
            return
        if obj.get("hello") or obj.get("dummy"):
            return
        text = obj.get("text")
        if not isinstance(text, str):
            return
        self.chat_screen.append_message(
            datetime.now(),
            crypto.fingerprint8(peer.ik_pub),
            text,
            is_self=False,
            trusted=peer.trusted,
        )

    async def _on_ws_closed(self, reason: str) -> None:
        if self._intentional_close:
            return
        self._initial_lobby_err = f"// disconnected ({reason})"
        await self._purge(send_leave=False)
        try:
            while len(self.screen_stack) > 1:
                self.pop_screen()
        except Exception:
            pass
        try:
            await self.push_screen(LobbyScreen(self.default_server, self._initial_lobby_err))
        except Exception:
            pass

    # ---------- peers / SAS ----------

    def list_peers(self) -> list[dict]:
        if not self.identity:
            return []
        out = []
        for uid, p in sorted(self.peer_sessions.items()):
            if p.ik_pub is None:
                continue
            words = sas_words(self.identity.ik_pub, p.ik_pub)
            out.append({
                "fp": crypto.fingerprint8(p.ik_pub),
                "trusted": p.trusted,
                "sas": words,
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

    # ---------- status footer logic ----------

    def ratchet_status(self) -> str:
        """Returns 'green', 'yellow' or 'red' based on peer DR readiness."""
        if not self.peer_sessions:
            return "green"
        any_failed = any(p.state == "failed" for p in self.peer_sessions.values())
        any_pending = any(p.dr is None and p.state != "failed" for p in self.peer_sessions.values())
        if any_failed:
            return "red"
        if any_pending:
            return "yellow"
        return "green"

    def _refresh_status(self) -> None:
        if self.chat_screen and self.chat_screen.is_mounted:
            self.chat_screen.refresh_status()

    # ---------- purge ----------

    async def _purge(self, send_leave: bool) -> None:
        self._intentional_close = True
        if self._cover is not None:
            try:
                await self._cover.stop()
            except Exception:
                pass
            self._cover = None
        if self.chat_screen is not None:
            try:
                self.chat_screen.purge_local()
            except Exception:
                pass
        if self.net:
            if send_leave and self.room_id:
                try:
                    await asyncio.wait_for(
                        self.net.send({"type": "leave", "roomId": self.room_id}),
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
        # Drop x3dh state & DR sessions by clearing the dict; Python GC handles the rest.
        self.peer_sessions = {}
        self.room_id = None
        self.room_display = None
        self.users = []
        self.self_uid = None
        self.chat_screen = None
        self.starmap_screen = None

    async def action_purge_quit(self) -> None:
        await self._purge(send_leave=True)
        self.exit()

    # ---------- helpers ----------

    def _return_to_lobby(self, err: str) -> None:
        if not self.screen_stack:
            return
        top = self.screen_stack[-1]
        if isinstance(top, LobbyScreen):
            try:
                from textual.widgets import Static
                top.query_one("#lobby-err", Static).update(f"// {err}")
            except Exception:
                pass


def _detect_compact() -> bool:
    try:
        import shutil
        return shutil.get_terminal_size((100, 24)).columns < 80
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser(prog="void", description="VOID ephemeral terminal messenger")
    ap.add_argument("--onion", default=None, metavar="ADDR.ONION:PORT",
                    help="server hidden service address (prompted in lobby if omitted)")
    ap.add_argument("--clearnet", action="store_true",
                    help="bypass Tor; connect directly (local testing only)")
    ap.add_argument("--server", default=None,
                    help="explicit ws(s):// server URL (overrides --onion routing)")
    ap.add_argument("--insecure", action="store_true",
                    help="allow ws:// or skip cert verification on wss://")
    ap.add_argument("--socks", default="socks5://127.0.0.1:9050",
                    help="SOCKS5 proxy URL used with --onion (default Tor)")
    ap.add_argument("--no-cover", action="store_true", help="disable cover-traffic dummies")
    ap.add_argument("--setup", action="store_true",
                    help="run interactive setup diagnostic and exit")
    ap.add_argument("--host", action="store_true",
                    help="run a void-server in this process (advanced)")
    ap.add_argument("--make-invite", action="store_true",
                    help="one-shot host: create an ephemeral .onion, run a server, "
                         "and print a void:// invite link")
    args = ap.parse_args()

    if args.setup:
        from . import setup_check
        sys.exit(setup_check.run())

    if args.make_invite:
        # Quick sanity: control port reachable? if not, give friendly error before
        # diving into the asyncio control client.
        from . import host as host_mod
        sys.exit(host_mod.run())

    if args.host:
        # Hand off to the server entry point. The user gets the server CLI
        # surface (--port, --cert, --key, --insecure, --no-jitter).
        from tools.void.server.main import main as server_main
        sys.argv = ["void-server"] + sys.argv[1:]
        sys.argv = [a for a in sys.argv if a != "--host"]
        server_main()
        return

    # Smart default: try Tor unless the user explicitly asked for clearnet.
    if not args.clearnet:
        from . import setup_check
        socks_port = setup_check.detect_socks_port()
        if socks_port is None:
            sys.stderr.write(
                "Tor not detected on 127.0.0.1 (tried 9050, 9150, 9151).\n"
                f"Install: {setup_check.install_hint()}\n"
                "Then re-run 'void'.  (Or pass --clearnet to skip Tor — NOT recommended.)\n"
            )
            sys.exit(1)
        # Auto-promote the discovered port unless the user overrode --socks.
        if args.socks == ap.get_default("socks"):
            args.socks = f"socks5://127.0.0.1:{socks_port}"

    onion_target = args.onion
    if onion_target:
        for pfx in ("ws://", "wss://", "http://", "https://"):
            if onion_target.startswith(pfx):
                onion_target = onion_target[len(pfx):]
        if ":" not in onion_target:
            onion_target = onion_target + ":8765"

    # Default server URL hint shown in the lobby.
    default_server = args.server or (
        f"ws://{onion_target}" if onion_target else "wss://localhost:8765"
    )

    os.environ.pop("TEXTUAL_LOG", None)

    app = VoidApp(
        server=default_server,
        insecure=args.insecure,
        onion_target=onion_target,
        clearnet=args.clearnet,
        socks_url=args.socks,
        cover_enabled=not args.no_cover,
    )
    app.compact = _detect_compact()

    try:
        loop = asyncio.get_event_loop_policy().get_event_loop()
        if sys.platform != "win32":
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, lambda: asyncio.ensure_future(app.action_purge_quit()))
                except (NotImplementedError, RuntimeError):
                    pass
    except Exception:
        pass

    try:
        app.run()
    except KeyboardInterrupt:
        try:
            asyncio.run(app._purge(send_leave=False))
        except Exception:
            pass


if __name__ == "__main__":
    main()
