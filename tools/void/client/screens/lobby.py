from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from babel.art import LOGO, SUB, HINTS, SCANLINE
from ..link import decode as decode_invite
from ..secure_mem import mlock_status
from .welcome import WelcomeScreen


def _is_ascii_printable(s: str) -> bool:
    return len(s) >= 1 and len(s) <= 64 and all(0x20 <= ord(c) <= 0x7E for c in s)


def _strip_url_prefix(s: str) -> str:
    for pfx in ("ws://", "wss://", "http://", "https://"):
        if s.startswith(pfx):
            return s[len(pfx):]
    return s


# Plain-language translations for common net / crypto failure modes.
PLAIN_ERRORS = {
    "ProxyConnectionError": "Could not reach Tor on your computer. Is Tor running?",
    "ConnectionRefusedError": "The server refused the connection. Wrong address or it's offline.",
    "TimeoutError": "Timed out reaching the server. Tor or the .onion may be unreachable.",
    "InvalidStatus": "The server didn't speak WebSocket. Check the address.",
    "OSError": "Network unavailable.",
    "ConnectionResetError": "The server closed the connection unexpectedly.",
    "ProxyError": "Tor was reached but refused to proxy. Try restarting Tor.",
    "WebSocketException": "Could not start a WebSocket session.",
    "InvalidMessage": "The server replied with something unrecognised.",
    "ConnectionClosedError": "Connection closed by the server.",
}


def translate_error(raw: str) -> str:
    for tag, friendly in PLAIN_ERRORS.items():
        if tag in raw:
            return friendly
    return raw


class LobbyScreen(Screen):
    BINDINGS = [
        Binding("ctrl+c", "app.purge_quit", "quit", priority=True, show=False),
        Binding("ctrl+q", "app.purge_quit", "quit", priority=True, show=False),
        Binding("question_mark", "help", "help", show=False),
        Binding("f1", "help", "help", show=False),
    ]

    def __init__(self, default_server: str, error: str | None = None) -> None:
        super().__init__()
        self._default_server = default_server
        self._initial_error = error
        self._swap_warning_armed = False

    def _compact(self) -> bool:
        return bool(getattr(self.app, "compact", False))

    def compose(self) -> ComposeResult:
        st = mlock_status()
        self._mlock_ok = bool(st["mlock_ok"])
        self._swap_active = bool(st["swap_active"])
        self._swap_warning_armed = self._swap_active and not self._mlock_ok

        with Container(id="lobby-container"):
            with Vertical(id="lobby-card"):
                yield Static(LOGO, id="logo", classes="title")
                if not self._compact():
                    yield Static(SUB, classes="sub")
                yield Static(SCANLINE, classes="scanline")
                yield Static(self._transport_label(), id="transport", classes=self._transport_class())
                yield Static(self._mem_label(), id="mem", classes=self._mem_class())
                yield Static(" ")

                yield Static("PASTE AN INVITE  (void://…)", classes="hint")
                yield Input(placeholder="void://…", id="invite", max_length=2048)
                yield Static(" — or —", classes="sub center")

                onion_default = ""
                onion = getattr(self.app, "onion_target", None)
                if onion:
                    onion_default = onion
                yield Static(".onion ADDRESS", classes="sub")
                yield Input(placeholder="xxxxx.onion:8765", id="server",
                            value=onion_default, max_length=120)
                yield Static("ROOM KEY", classes="sub")
                yield Input(placeholder="any short name you both agree on", id="room", max_length=64)
                yield Static("PASSWORD", classes="sub")
                yield Input(placeholder="any short secret you both agree on",
                            id="pw", password=True, max_length=64)
                yield Static(" ")
                yield Button("ENTER", id="enter", variant="success")
                yield Static(self._initial_error or "", id="lobby-err", classes="err")
                yield Static(f"// {random.choice(HINTS)}      [?] first-time help",
                             id="hint", classes="hint")

    # ---------- labels ----------

    def _transport_label(self) -> str:
        if getattr(self.app, "clearnet", False):
            return "TRANSPORT: CLEARNET  (insecure — local dev only)"
        return "TRANSPORT: ONION  (routed through Tor)"

    def _transport_class(self) -> str:
        return "blink-err" if getattr(self.app, "clearnet", False) else "ok"

    def _mem_label(self) -> str:
        if self._swap_active and not self._mlock_ok:
            return "⚠  swap is active and memory locking failed — confirm below to continue"
        if self._swap_active and self._mlock_ok:
            return "swap: detected, mlock: ok"
        if self._mlock_ok:
            return "mlock: ok"
        return "mlock: unavailable (swap inactive — lower risk)"

    def _mem_class(self) -> str:
        return "err" if (self._swap_active and not self._mlock_ok) else "sub"

    # ---------- mounting ----------

    def on_mount(self) -> None:
        # Focus the invite field first — that's the easy path.
        try:
            self.query_one("#invite", Input).focus()
        except Exception:
            pass

    def action_help(self) -> None:
        try:
            self.app.push_screen(WelcomeScreen())
        except Exception:
            pass

    # ---------- invite paste autofill ----------

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "invite":
            return
        val = event.value.strip()
        if not val:
            return
        inv = decode_invite(val)
        if inv is None:
            return
        # Autofill the three fields from a valid invite.
        self.query_one("#server", Input).value = inv.onion
        self.query_one("#room", Input).value = inv.room
        self.query_one("#pw", Input).value = inv.password
        if inv.expected_fp:
            self.app.expected_fp = inv.expected_fp
        err = self.query_one("#lobby-err", Static)
        err.update("// invite accepted. press ENTER to join.")

    # ---------- enter ----------

    def _autofill_from_invite(self) -> bool:
        """If the invite field has a valid void:// link, fill the other
        three fields from it (overwriting any prior values). Returns True
        if an invite was applied."""
        try:
            invite_val = self.query_one("#invite", Input).value.strip()
        except Exception:
            return False
        if not invite_val:
            return False
        inv = decode_invite(invite_val)
        if inv is None:
            return False
        self.query_one("#server", Input).value = inv.onion
        self.query_one("#room", Input).value = inv.room
        self.query_one("#pw", Input).value = inv.password
        if inv.expected_fp:
            self.app.expected_fp = inv.expected_fp
        return True

    async def _try_enter(self) -> None:
        # If the invite field is populated, treat it as authoritative.
        self._autofill_from_invite()
        room = self.query_one("#room", Input).value
        pw = self.query_one("#pw", Input).value
        server_in = self.query_one("#server", Input).value.strip()
        err = self.query_one("#lobby-err", Static)

        if not _is_ascii_printable(room):
            err.update("// room key must be 1-64 printable characters")
            return
        if not _is_ascii_printable(pw):
            err.update("// password must be 1-64 printable characters")
            return

        clearnet = bool(getattr(self.app, "clearnet", False))
        if clearnet:
            if not server_in:
                err.update("// type a server URL (e.g. ws://127.0.0.1:8765)")
                return
            if not (server_in.startswith("ws://") or server_in.startswith("wss://")):
                server_in = "ws://" + server_in
        else:
            host = _strip_url_prefix(server_in)
            if not host or ".onion" not in host:
                err.update("// the address must end in .onion (e.g. xxxxx.onion:8765)")
                return
            if ":" not in host:
                host = host + ":8765"
            self.app.onion_target = host
            server_in = f"ws://{host}"

        if self._swap_warning_armed:
            if not room.startswith("!ack-"):
                err.update("⚠  to continue with swap+mlock danger, prefix room key with '!ack-'")
                return
            room = room[len("!ack-"):]
            if not _is_ascii_printable(room):
                err.update("// invalid room key after !ack- prefix")
                return

        err.update("// connecting...")
        await self.app.enter_room(room, pw, server_in)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "enter":
            await self._try_enter()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._try_enter()
