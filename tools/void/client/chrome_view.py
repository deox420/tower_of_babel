"""In-chrome VOID view.

The babel suite menu mounts this in its content slot when the user
picks a VOID entry. It is the second front-end over
:class:`tools.void.client.session.VoidSession` (the first is the
standalone :class:`tools.void.client.app.VoidApp`), so the transport +
crypto code is shared and audited once.

VOID is a SERVICE-flavour tool: backgrounding it (Alt+0) keeps the
room alive in a slot; the chrome calls :meth:`purge_local` on close /
quit to wipe RAM. The view drives three swappable stages inside its own
content area — lobby → connecting → chat — instead of the screen stack
the standalone client uses.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Button, Input, RichLog, Static

from babel import art
from babel.views import ToolHomeView

from .link import decode as decode_invite
from .screens.chat import HELP_TEXT, LineEntry
from .screens.connecting import STEPS as CONN_STEPS
from .screens.lobby import (
    _is_ascii_printable,
    _strip_url_prefix,
)
from .session import VoidSession
from .setup_check import detect_socks_port


# ---------------------------------------------------------------------------
# Stage: lobby
# ---------------------------------------------------------------------------


class _LobbyStage(Vertical):
    """Room entry: paste an invite, or fill onion/room/password."""

    def __init__(self, view: "VoidView", error: str | None = None) -> None:
        super().__init__(id="void-lobby")
        self._view = view
        self._error = error

    def compose(self) -> ComposeResult:
        yield Static("// VOID — ephemeral encrypted messenger", classes="void-title")
        yield Static(self._view.transport_label(), id="void-transport",
                     classes="void-sub")
        yield Static("PASTE AN INVITE  (void://…)", classes="void-hint")
        yield Input(placeholder="void://…", id="void-invite", max_length=2048)
        yield Static("— or —", classes="void-sub")
        yield Input(placeholder="xxxxx.onion:8765  (server address)",
                    id="void-server", max_length=120)
        yield Input(placeholder="room key (both peers agree)", id="void-room",
                    max_length=64)
        yield Input(placeholder="password (both peers agree)", id="void-pw",
                    password=True, max_length=64)
        with Vertical(id="void-lobby-buttons"):
            yield Button("ENTER", id="void-enter", variant="success")
            yield Button(self._transport_button_label(), id="void-transport-toggle")
        yield Static(self._error or "", id="void-lobby-err", classes="void-err")

    def _transport_button_label(self) -> str:
        return "[ Transport: CLEARNET ]" if self._view.session.clearnet \
            else "[ Transport: ONION (Tor) ]"

    def on_mount(self) -> None:
        try:
            self.query_one("#void-invite", Input).focus()
        except Exception:
            pass

    def _set_err(self, msg: str) -> None:
        try:
            self.query_one("#void-lobby-err", Static).update(msg)
        except Exception:
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "void-invite":
            return
        val = event.value.strip()
        if not val:
            return
        inv = decode_invite(val)
        if inv is None:
            return
        self.query_one("#void-server", Input).value = inv.onion
        self.query_one("#void-room", Input).value = inv.room
        self.query_one("#void-pw", Input).value = inv.password
        if inv.expected_fp:
            self._view.session.expected_fp = inv.expected_fp
        self._set_err("// invite accepted. press ENTER to join.")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "void-enter":
            await self._try_enter()
        elif event.button.id == "void-transport-toggle":
            self._view.session.clearnet = not self._view.session.clearnet
            self.query_one("#void-transport-toggle", Button).label = \
                self._transport_button_label()
            self.query_one("#void-transport", Static).update(
                self._view.transport_label())

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._try_enter()

    async def _try_enter(self) -> None:
        room = self.query_one("#void-room", Input).value
        pw = self.query_one("#void-pw", Input).value
        server_in = self.query_one("#void-server", Input).value.strip()
        if not _is_ascii_printable(room):
            self._set_err("// room key must be 1-64 printable characters")
            return
        if not _is_ascii_printable(pw):
            self._set_err("// password must be 1-64 printable characters")
            return

        if self._view.session.clearnet:
            if not server_in:
                self._set_err("// type a server URL (e.g. ws://127.0.0.1:8765)")
                return
            if not (server_in.startswith("ws://") or server_in.startswith("wss://")):
                server_in = "ws://" + server_in
        else:
            host = _strip_url_prefix(server_in)
            if not host or ".onion" not in host:
                self._set_err("// the address must end in .onion (e.g. xxxxx.onion:8765)")
                return
            if ":" not in host:
                host = host + ":8765"
            self._view.session.onion_target = host
            server_in = f"ws://{host}"

        self._set_err("// connecting...")
        await self._view.session.enter_room(room, pw, server_in)


# ---------------------------------------------------------------------------
# Stage: connecting
# ---------------------------------------------------------------------------


class _ConnectingStage(Vertical):
    def __init__(self, view: "VoidView") -> None:
        super().__init__(id="void-connecting")
        self._view = view
        self._current = 0
        self._failed = False
        self._failure = ""

    def compose(self) -> ComposeResult:
        yield Static("// ESTABLISHING CHANNEL //", classes="void-title")
        # NB: do NOT name the builder ``_render`` — Textual's Widget._render()
        # is an internal hook that must return a Visual, not our markup str.
        yield Static(self._steps_markup(), id="void-conn-steps")

    def set_step(self, idx: int) -> None:
        self._current = idx
        self._update()

    def set_failed(self, msg: str) -> None:
        self._failed = True
        self._failure = msg
        self._update()

    def _update(self) -> None:
        try:
            self.query_one("#void-conn-steps", Static).update(self._steps_markup())
        except Exception:
            pass

    def _steps_markup(self) -> str:
        # Textual content markup (markup=True), so markers avoid literal
        # square brackets — those would be parsed as markup tags.
        out: list[str] = []
        for i, label in enumerate(CONN_STEPS):
            if self._failed and i == self._current:
                marker, color = "✗", "#ff3860"
            elif i < self._current:
                marker, color = "✓", "#00ff9c"
            elif i == self._current:
                marker, color = "▶", "#6cdcff"
            else:
                marker, color = "·", "#7a7a7a"
            out.append(f"  [bold {color}]{marker}[/]  {label}")
        block = "\n".join(out)
        if self._failed and self._failure:
            block += f"\n\n  [bold #ff3860]// {self._failure}[/]"
        return block


# ---------------------------------------------------------------------------
# Stage: chat
# ---------------------------------------------------------------------------


class _ChatStage(Vertical):
    def __init__(self, view: "VoidView", room_display: str) -> None:
        super().__init__(id="void-chat")
        self._view = view
        self._room_display = room_display
        self._lines: list[LineEntry] = []
        self.burn_seconds: int | None = None

    def compose(self) -> ComposeResult:
        yield Static(self._header_text(), id="void-chat-header")
        yield RichLog(id="void-chat-log", wrap=True, markup=False, highlight=False)
        yield Input(placeholder="say something into the void...", id="void-chat-input")
        yield Static("", id="void-chat-footer")

    def on_mount(self) -> None:
        self.refresh_header()
        self.refresh_status()
        self.append_system("connected. messages are end-to-end encrypted.")
        self.append_system("only nodes with this room key + password can read this.")
        try:
            self.query_one("#void-chat-input", Input).focus()
        except Exception:
            pass

    # ----- header / footer -----

    def _header_text(self) -> str:
        fp = self._view.session.identity_fp_or("--------")
        return f"// room: {self._room_display}    fp: {fp}    /help"

    def refresh_header(self) -> None:
        try:
            self.query_one("#void-chat-header", Static).update(self._header_text())
        except Exception:
            pass

    def refresh_status(self) -> None:
        s = self._view.session
        onion = bool(s.onion_target) and not s.clearnet
        cover_on = bool(s.cover_enabled)
        ratchet_state = s.ratchet_status()
        tor_color = "#00ff9c" if onion else "#ff3860"
        cover_color = "#00ff9c" if cover_on else "#7a7a7a"
        ratchet_color = {"green": "#00ff9c", "yellow": "#ffd166",
                         "red": "#ff3860"}.get(ratchet_state, "#7a7a7a")
        # Textual content markup (the footer Static keeps markup=True). No
        # literal brackets in the labels, so nothing needs escaping.
        parts = [
            f"[bold {tor_color}]{'TOR' if onion else 'CLR'}[/]",
            "[bold #00ff9c]PAD[/]",
            f"[bold {cover_color}]{'COVER' if cover_on else 'no-cover'}[/]",
            f"[bold {ratchet_color}]RATCHET[/]",
        ]
        if self.burn_seconds is not None:
            parts.append(f"[bold #ffd166]BURN {self.burn_seconds}s[/]")
        markup = "  ·  ".join(parts)
        try:
            self.query_one("#void-chat-footer", Static).update(markup)
        except Exception:
            pass

    # ----- log model -----

    def append_system(self, line: str, *, error: bool = False) -> None:
        self._lines.append(LineEntry(kind="system",
                                     text_buf=bytearray(line.encode()),
                                     error=error))
        self._redraw()

    def append_message(self, ts: datetime, fp: str, text: str, *,
                       is_self: bool, trusted: bool) -> None:
        entry = LineEntry(kind="msg", ts=ts, fp=fp, is_self=is_self,
                          trusted=trusted, text_buf=bytearray(text.encode("utf-8")))
        if is_self and self.burn_seconds is not None:
            entry.burn_task = asyncio.create_task(
                self._burn_after(entry, self.burn_seconds))
        self._lines.append(entry)
        self._redraw()

    async def _burn_after(self, entry: LineEntry, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        if entry.text_buf is not None:
            for i in range(len(entry.text_buf)):
                entry.text_buf[i] = 0
        entry.kind = "burned"
        try:
            self._redraw()
        except Exception:
            pass

    def _redraw(self) -> None:
        try:
            log = self.query_one("#void-chat-log", RichLog)
        except Exception:
            return
        log.clear()
        for e in self._lines:
            if e.kind == "system":
                style = "#ff3860 bold" if e.error else "dim #6cdcff"
                log.write(Text(f"// {e.text_buf.decode('utf-8', errors='replace')}",
                               style=style))
            elif e.kind == "msg":
                ts_s = e.ts.strftime("%H:%M") if e.ts else "--:--"
                fp = e.fp[:8]
                prefix = Text(f"[{ts_s}] ", style="dim #6cdcff")
                star = Text("✦ ", style="bold #6cdcff") if e.trusted else Text("")
                tag_color = "bold #6cdcff" if (e.is_self or e.trusted) else "bold #00ff9c"
                tag = Text(f"<{fp}> ", style=tag_color)
                body = Text(e.text_buf.decode("utf-8", errors="replace")
                            if e.text_buf else "", style="#00ff9c")
                log.write(prefix + star + tag + body)
            elif e.kind == "burned":
                ts_s = e.ts.strftime("%H:%M") if e.ts else "--:--"
                log.write(Text(f"[{ts_s}] <{e.fp[:8]}> [BURNED]",
                               style="dim #7a7a7a"))

    # ----- input / commands -----

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        self.query_one("#void-chat-input", Input).value = ""
        if not text:
            return
        if text.startswith("/"):
            await self._handle_command(text.strip())
            return
        await self._view.session.send_message(text)

    async def _handle_command(self, cmd: str) -> None:
        parts = cmd.split(None, 1)
        head = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""
        s = self._view.session
        if head == "/leave":
            await s.leave_room()
        elif head == "/quit":
            await s.quit()
        elif head == "/help":
            for line in HELP_TEXT.splitlines():
                self.append_system(line)
        elif head == "/whoami":
            self.append_system(f"local fingerprint: {s.identity_full_fp_or('?')}")
        elif head == "/peers" or head == "/map":
            self._render_peers()
        elif head == "/verify":
            self._render_verify(arg)
        elif head == "/trust":
            self._render_trust(arg)
        elif head == "/burn":
            self._handle_burn(arg)
        else:
            self.append_system(f"unknown command: {cmd}", error=True)

    def _render_peers(self) -> None:
        peers = self._view.session.list_peers()
        if not peers:
            self.append_system("no peers seen in this room yet.")
            return
        self.append_system("peers in this room:")
        for p in peers:
            status = "TRUSTED" if p["trusted"] else "UNVERIFIED"
            words = " · ".join(p["sas"])
            self.append_system(f"  <{p['fp'][:8]}>  {status:11s}  SAS: {words}")

    def _render_verify(self, arg: str) -> None:
        if not arg:
            self.append_system("usage: /verify <fp8>", error=True)
            return
        info = self._view.session.peer_sas(arg)
        if info is None:
            self.append_system(f"unknown peer fp: {arg}", error=True)
            return
        self.append_system(f"SAS for peer <{arg}>:")
        self.append_system(f"   {' · '.join(info['sas'])}")
        self.append_system("compare these 5 words with your peer over an external channel.")
        self.append_system(f"if they match, run:  /trust {arg}")

    def _render_trust(self, arg: str) -> None:
        if not arg:
            self.append_system("usage: /trust <fp8>", error=True)
            return
        if self._view.session.mark_trusted(arg):
            self.append_system(f"peer <{arg}> marked TRUSTED for this session.")
        else:
            self.append_system(f"unknown peer fp: {arg}", error=True)

    def _handle_burn(self, arg: str) -> None:
        if not arg:
            state = "OFF" if self.burn_seconds is None else f"ON, {self.burn_seconds}s"
            self.append_system(f"burn: {state}.  enable with: /burn <seconds 10..86400>")
            return
        if arg.lower() == "off":
            self.burn_seconds = None
            self.refresh_status()
            self.append_system("burn: OFF")
            return
        try:
            n = int(arg)
        except ValueError:
            self.append_system("usage: /burn <seconds 10..86400> | off", error=True)
            return
        if not (10 <= n <= 86400):
            self.append_system("burn seconds must be between 10 and 86400", error=True)
            return
        self.burn_seconds = n
        self.refresh_status()
        self.append_system(f"burn: ON, {n}s — your future messages disappear locally.")

    def purge_local(self) -> None:
        for e in self._lines:
            if e.burn_task is not None and not e.burn_task.done():
                e.burn_task.cancel()
            if e.text_buf is not None:
                for i in range(len(e.text_buf)):
                    e.text_buf[i] = 0
        self._lines.clear()


# ---------------------------------------------------------------------------
# VoidView — the in-chrome host + VoidUI implementation
# ---------------------------------------------------------------------------


class VoidView(ToolHomeView):
    """In-chrome VOID. Owns a session and swaps lobby/connecting/chat stages."""

    name: ClassVar[str] = "VOID"
    flavour: ClassVar[str] = "SERVICE"
    logo: ClassVar[str] = art.VOID_LOGO

    BINDINGS = [
        Binding("escape", "leave", "background to slot", show=True, priority=True),
        Binding("alt+0",  "leave", "menu",              show=False, priority=True),
    ]

    DEFAULT_CSS = ToolHomeView.DEFAULT_CSS + """
    VoidView { padding: 0 1; }
    VoidView #void-slot { height: 1fr; width: 1fr; }
    VoidView .void-title { color: #6cdcff; text-style: bold; width: 100%; }
    VoidView .void-sub { color: #7a7a7a; width: 100%; }
    VoidView .void-hint { color: #00ff9c; width: 100%; margin-top: 1; }
    VoidView .void-err { color: #ff3860; width: 100%; }
    VoidView #void-lobby Input { margin: 0 0 1 0; }
    VoidView #void-lobby-buttons { height: auto; }
    VoidView #void-chat-log { height: 1fr; border: round #1a3a2a; }
    VoidView #void-chat-header { color: #6cdcff; }
    """

    def __init__(self) -> None:
        super().__init__()
        socks_port = detect_socks_port()
        socks_url = f"socks5://127.0.0.1:{socks_port or 9050}"
        # Default to Tor; the lobby exposes a CLEARNET toggle for local use.
        self.session = VoidSession(
            self,
            server="",
            insecure=True,
            onion_target=None,
            clearnet=False,
            socks_url=socks_url,
            cover_enabled=True,
        )
        self._slot: Vertical | None = None
        self._lobby: _LobbyStage | None = None
        self._connecting: _ConnectingStage | None = None
        self._chat: _ChatStage | None = None

    # ----- compose / stage management -----

    def compose(self) -> ComposeResult:
        self._slot = Vertical(id="void-slot")
        yield self._slot

    def on_mount(self) -> None:
        self._show_lobby(None)
        try:
            self.focus()
        except Exception:
            pass

    async def _swap(self, stage) -> None:
        if self._slot is None:
            return
        await self._slot.remove_children()
        await self._slot.mount(stage)

    def _show_lobby(self, error: str | None) -> None:
        self._chat = None
        self._connecting = None
        self._lobby = _LobbyStage(self, error)
        asyncio.ensure_future(self._swap(self._lobby))

    def transport_label(self) -> str:
        if self.session.clearnet:
            return "TRANSPORT: CLEARNET  (insecure — local dev only)"
        return "TRANSPORT: ONION  (routed through Tor)"

    # ----- VoidUI callbacks -----

    def on_connecting_start(self) -> None:
        self._connecting = _ConnectingStage(self)
        asyncio.ensure_future(self._swap(self._connecting))

    def on_connecting_step(self, idx: int) -> None:
        if self._connecting is not None:
            self._connecting.set_step(idx)

    def on_connecting_failed(self, msg: str) -> None:
        if self._connecting is not None:
            self._connecting.set_failed(msg)

    def on_enter_chat(self, room_display: str) -> None:
        self._connecting = None
        self._chat = _ChatStage(self, room_display)
        asyncio.ensure_future(self._swap(self._chat))

    def on_return_to_lobby(self, error: str | None) -> None:
        if self._chat is not None:
            try:
                self._chat.purge_local()
            except Exception:
                pass
        self._show_lobby(error)

    def on_system(self, text: str, *, error: bool = False) -> None:
        if self._chat is not None and self._chat.is_mounted:
            self._chat.append_system(text, error=error)

    def on_message(self, ts: datetime, fp: str, text: str, *,
                   is_self: bool, trusted: bool) -> None:
        if self._chat is not None and self._chat.is_mounted:
            self._chat.append_message(ts, fp, text, is_self=is_self, trusted=trusted)

    def on_status_changed(self) -> None:
        if self._chat is not None and self._chat.is_mounted:
            self._chat.refresh_status()

    def on_users_changed(self, users: list[str]) -> None:
        # In-chrome has no separate star-map; /map renders the peer list
        # inline. Refresh the footer so the ratchet/peer indicator tracks.
        self.on_status_changed()

    def on_quit(self) -> None:
        # /quit inside the chat: purge already ran in session.quit(); hand
        # control back to the menu (tearing down this service slot).
        self.action_leave()

    # ----- Service Protocol -----

    def status_line(self) -> str:
        s = self.session
        if not s.in_room():
            return "lobby"
        n = len([p for p in s.peer_sessions.values() if p.ik_pub is not None])
        room = s.room_display or "?"
        return f"room {room} · {n} peer{'s' if n != 1 else ''}"

    async def purge_local(self) -> None:
        if self._chat is not None:
            try:
                self._chat.purge_local()
            except Exception:
                pass
        try:
            await self.session.purge(send_leave=True)
        except Exception:
            pass


__all__ = ["VoidView"]
