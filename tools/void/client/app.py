"""VOID standalone client — Textual front-end over :class:`VoidSession`.

All transport + X3DH + Double Ratchet orchestration lives in
``tools.void.client.session.VoidSession``; this module is the
screen-stack front-end (``babel --exec void``). It implements the
:class:`VoidUI` callback surface by driving its lobby / connecting /
chat / starmap screens, and delegates every protocol action to the
session. The in-chrome view (``chrome_view.VoidView``) is a second
front-end over the same controller.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import sys
from datetime import datetime

from textual.app import App

from .net import Net  # noqa: F401  (kept for backwards-compat re-export)
from .screens.chat import ChatScreen
from .screens.connecting import ConnectingScreen
from .screens.lobby import LobbyScreen
from .screens.starmap import StarMapScreen
from .session import VoidSession


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
        self.session = VoidSession(
            self,
            server=server,
            insecure=insecure,
            onion_target=onion_target,
            clearnet=clearnet,
            socks_url=socks_url,
            cover_enabled=cover_enabled,
        )
        self._initial_lobby_err: str | None = None
        self.chat_screen: ChatScreen | None = None
        self.starmap_screen: StarMapScreen | None = None
        self._connecting: ConnectingScreen | None = None
        self.compact: bool = False

    # ---------- config the screens read off ``self.app`` ----------
    #
    # The lobby/chat screens were written against ``VoidApp`` directly
    # (e.g. ``self.app.onion_target``); these properties keep that
    # surface working while the real state lives on the session.

    @property
    def default_server(self) -> str:
        return self.session.default_server

    @property
    def clearnet(self) -> bool:
        return self.session.clearnet

    @property
    def cover_enabled(self) -> bool:
        return self.session.cover_enabled

    @property
    def onion_target(self) -> str | None:
        return self.session.onion_target

    @onion_target.setter
    def onion_target(self, value: str | None) -> None:
        self.session.onion_target = value

    @property
    def expected_fp(self) -> str | None:
        return self.session.expected_fp

    @expected_fp.setter
    def expected_fp(self, value: str | None) -> None:
        self.session.expected_fp = value

    # ---------- lifecycle ----------

    def on_mount(self) -> None:
        self.push_screen(LobbyScreen(self.default_server, self._initial_lobby_err))
        self._initial_lobby_err = None

    # ---------- delegating actions (called from screens) ----------

    def identity_fp_or(self, default: str) -> str:
        return self.session.identity_fp_or(default)

    def identity_full_fp_or(self, default: str) -> str:
        return self.session.identity_full_fp_or(default)

    async def enter_room(self, room_key: str, password: str, server_url: str) -> None:
        await self.session.enter_room(room_key, password, server_url)

    async def send_message(self, text: str) -> None:
        await self.session.send_message(text)

    async def leave_room(self) -> None:
        await self.session.leave_room()

    def list_peers(self) -> list[dict]:
        return self.session.list_peers()

    def peer_sas(self, fp8: str) -> dict | None:
        return self.session.peer_sas(fp8)

    def mark_trusted(self, fp8: str) -> bool:
        return self.session.mark_trusted(fp8)

    def ratchet_status(self) -> str:
        return self.session.ratchet_status()

    async def open_map(self) -> None:
        if self.starmap_screen is None:
            self.starmap_screen = StarMapScreen()
        await self.push_screen(self.starmap_screen)
        self.starmap_screen.update_users(self.session.users)

    async def action_purge_quit(self) -> None:
        await self.session.quit()

    # ---------- VoidUI callbacks (driven by the session) ----------

    def on_system(self, text: str, *, error: bool = False) -> None:
        if self.chat_screen is not None and self.chat_screen.is_mounted:
            self.chat_screen.append_system(text, error=error)

    def on_message(self, ts: datetime, fp: str, text: str, *,
                   is_self: bool, trusted: bool) -> None:
        if self.chat_screen is not None and self.chat_screen.is_mounted:
            self.chat_screen.append_message(ts, fp, text, is_self=is_self,
                                            trusted=trusted)

    def on_status_changed(self) -> None:
        if self.chat_screen is not None and self.chat_screen.is_mounted:
            self.chat_screen.refresh_status()

    def on_connecting_start(self) -> None:
        # push_screen schedules the mount; the screen's own on_mount starts
        # the spinner, and set_step/set_failed are guarded against the
        # not-yet-mounted window — so no await is needed here.
        self._connecting = ConnectingScreen()
        self.push_screen(self._connecting)

    def on_connecting_step(self, idx: int) -> None:
        if self._connecting is not None:
            try:
                self._connecting.set_step(idx)
            except Exception:
                pass

    def on_connecting_failed(self, msg: str) -> None:
        if self._connecting is not None:
            try:
                self._connecting.set_failed(msg)
            except Exception:
                pass

    def on_enter_chat(self, room_display: str) -> None:
        self._pop_transient()
        chat = ChatScreen(room_key_display=room_display)
        self.chat_screen = chat
        # ChatScreen.on_mount calls refresh_header()/refresh_status() itself.
        self.push_screen(chat)

    def on_return_to_lobby(self, error: str | None) -> None:
        if self.chat_screen is not None:
            try:
                self.chat_screen.purge_local()
            except Exception:
                pass
        self.chat_screen = None
        self.starmap_screen = None
        self._connecting = None
        try:
            while len(self.screen_stack) > 1:
                self.pop_screen()
        except Exception:
            pass
        if error:
            self._initial_lobby_err = error
        try:
            self.push_screen(LobbyScreen(self.default_server, error))
        except Exception:
            pass

    def on_users_changed(self, users: list[str]) -> None:
        if self.starmap_screen is not None and self.starmap_screen.is_mounted:
            self.starmap_screen.update_users(users)

    def on_quit(self) -> None:
        self.exit()

    def _pop_transient(self) -> None:
        """Drop the connecting screen if it's on top."""
        self._connecting = None
        try:
            if len(self.screen_stack) > 1:
                top = self.screen_stack[-1]
                if isinstance(top, ConnectingScreen):
                    self.pop_screen()
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
        from . import host as host_mod
        sys.exit(host_mod.run())

    if args.host:
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
        if args.socks == ap.get_default("socks"):
            args.socks = f"socks5://127.0.0.1:{socks_port}"

    onion_target = args.onion
    if onion_target:
        for pfx in ("ws://", "wss://", "http://", "https://"):
            if onion_target.startswith(pfx):
                onion_target = onion_target[len(pfx):]
        if ":" not in onion_target:
            onion_target = onion_target + ":8765"

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
            asyncio.run(app.session.purge(send_leave=False))
        except Exception:
            pass


if __name__ == "__main__":
    main()
