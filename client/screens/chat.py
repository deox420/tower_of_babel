from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Input, RichLog, Static


HELP_TEXT = (
    "/leave              purge this room, return to lobby\n"
    "/map                open the interstellar map\n"
    "/quit               purge and close VOID\n"
    "/whoami             show your full 64-hex IDENTITY (IK) fingerprint\n"
    "/peers              list peers with status and SAS words\n"
    "/verify <fp8>       show 5-word SAS for a peer (compare out-of-band)\n"
    "/trust <fp8>        mark peer as TRUSTED after SAS comparison\n"
    "/burn <seconds>     start a disappearing-message timer (10-86400, off, status)\n"
    "/help               this list\n"
    "verify locks in identity (IK), not session — re-verify per session.\n"
    "Ctrl+J / Alt+Enter  newline in input"
)


@dataclass
class LineEntry:
    """One renderable line in the chat log."""
    kind: str                      # 'system' | 'msg' | 'burned'
    ts: Optional[datetime] = None
    fp: str = ""
    is_self: bool = False
    trusted: bool = False
    text_buf: Optional[bytearray] = None
    error: bool = False
    burn_at: Optional[float] = None
    burn_task: Optional[asyncio.Task] = None


class ChatScreen(Screen):
    BINDINGS = [
        Binding("ctrl+c", "app.purge_quit", "quit", priority=True, show=False),
        Binding("ctrl+q", "app.purge_quit", "quit", priority=True, show=False),
        Binding("escape", "noop", show=False),
    ]

    def __init__(self, room_key_display: str) -> None:
        super().__init__()
        self._room_display = room_key_display
        self._lines: list[LineEntry] = []
        self.burn_seconds: int | None = None

    # ---------- composition ----------

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._header_text(), id="chat-header")
            yield RichLog(id="chat-log", wrap=True, markup=False, highlight=False)
            yield Input(placeholder="say something into the void...", id="chat-input")
            yield Static("", id="status-footer")

    def _compact(self) -> bool:
        return bool(getattr(self.app, "compact", False))

    def _fp_short(self, fp: str) -> str:
        return fp[:4] if self._compact() else fp[:8]

    def _header_text(self) -> str:
        fp = self.app.identity_fp_or("--------")
        fp = self._fp_short(fp) if self._compact() else fp
        if self._compact():
            return f"{self._room_display[:16]} {fp} /help"
        return f"// room: {self._room_display}    fp: {fp}    /help"

    def on_mount(self) -> None:
        self.refresh_header()
        self.refresh_status()
        self._append_system_line("connected. messages are end-to-end encrypted.")
        self._append_system_line("only nodes with this room key + password can read this.")
        self._redraw()
        self.query_one("#chat-input", Input).focus()

    def refresh_header(self) -> None:
        self.query_one("#chat-header", Static).update(self._header_text())

    # ---------- status footer ----------

    def refresh_status(self) -> None:
        app = self.app
        onion = bool(getattr(app, "onion_target", None))
        cover_on = bool(getattr(app, "cover_enabled", False))
        ratchet_state = getattr(app, "ratchet_status", lambda: "green")()
        tor_color = "#00ff9c" if onion else "#ff3860"
        cover_color = "#00ff9c" if cover_on else "#7a7a7a"
        ratchet_color = {
            "green": "#00ff9c", "yellow": "#ffd166", "red": "#ff3860",
        }.get(ratchet_state, "#7a7a7a")

        text = Text()
        if self._compact():
            # T·P·C·R compressed indicator strip.
            for label, color in [
                ("T", tor_color),
                ("P", "#00ff9c"),
                ("C", cover_color),
                ("R", ratchet_color),
            ]:
                text.append(label, style=f"bold {color}")
                text.append("·", style="dim #6cdcff")
            # burn indicator
            if self.burn_seconds is not None:
                text.append(f" burn:{self.burn_seconds}s", style="bold #ffd166")
        else:
            text.append("[", style="dim #6cdcff")
            text.append("TOR" if onion else "CLR", style=f"bold {tor_color}")
            text.append("]  [", style="dim #6cdcff")
            text.append("PAD", style="bold #00ff9c")
            text.append("]  [", style="dim #6cdcff")
            text.append("COVER" if cover_on else "no-cover", style=f"bold {cover_color}")
            text.append("]  [", style="dim #6cdcff")
            text.append("RATCHET", style=f"bold {ratchet_color}")
            text.append("]", style="dim #6cdcff")
            if self.burn_seconds is not None:
                text.append("  [", style="dim #6cdcff")
                text.append(f"BURN {self.burn_seconds}s", style="bold #ffd166")
                text.append("]", style="dim #6cdcff")
        self.query_one("#status-footer", Static).update(text)

    # ---------- log model ----------

    def _append_system_line(self, line: str, error: bool = False) -> None:
        self._lines.append(LineEntry(kind="system", text_buf=bytearray(line.encode()), error=error))

    def append_system(self, line: str, error: bool = False) -> None:
        self._append_system_line(line, error)
        self._redraw()

    def append_multiline(self, lines: list[str], *, color: str = "#6cdcff") -> None:
        for line in lines:
            self._append_system_line(line)
        self._redraw()

    def append_message(
        self,
        ts: datetime,
        fp: str,
        text: str,
        is_self: bool,
        trusted: bool = False,
    ) -> None:
        text_buf = bytearray(text.encode("utf-8"))
        entry = LineEntry(
            kind="msg", ts=ts, fp=fp, is_self=is_self, trusted=trusted, text_buf=text_buf
        )
        if is_self and self.burn_seconds is not None:
            entry.burn_task = asyncio.create_task(self._burn_after(entry, self.burn_seconds))
        self._lines.append(entry)
        self._redraw()

    async def _burn_after(self, entry: LineEntry, seconds: int) -> None:
        try:
            await asyncio.sleep(seconds)
        except asyncio.CancelledError:
            return
        # Zero the plaintext buffer and flip to burned state.
        if entry.text_buf is not None:
            for i in range(len(entry.text_buf)):
                entry.text_buf[i] = 0
        entry.kind = "burned"
        try:
            self._redraw()
        except Exception:
            pass

    def _redraw(self) -> None:
        log = self.query_one("#chat-log", RichLog)
        log.clear()
        for e in self._lines:
            if e.kind == "system":
                style = "#ff3860 bold" if e.error else "dim #6cdcff"
                line = Text(f"// {e.text_buf.decode('utf-8', errors='replace')}", style=style)
                log.write(line)
            elif e.kind == "msg":
                ts_s = e.ts.strftime("%H:%M") if e.ts else "--:--"
                fp = self._fp_short(e.fp)
                prefix = Text(f"[{ts_s}] ", style="dim #6cdcff")
                star = Text("✦ ", style="bold #6cdcff") if e.trusted else Text("", style="")
                tag_color = "bold #6cdcff" if (e.is_self or e.trusted) else "bold #00ff9c"
                tag = Text(f"<{fp}> ", style=tag_color)
                body_str = e.text_buf.decode("utf-8", errors="replace") if e.text_buf else ""
                body = Text(body_str, style="#00ff9c")
                log.write(prefix + star + tag + body)
            elif e.kind == "burned":
                ts_s = e.ts.strftime("%H:%M") if e.ts else "--:--"
                fp = self._fp_short(e.fp)
                line = Text(
                    f"[{ts_s}] <{fp}> [BURNED]", style="dim #7a7a7a"
                )
                log.write(line)

    # ---------- input ----------

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value
        inp = self.query_one("#chat-input", Input)
        inp.value = ""
        if not text:
            return
        if text.startswith("/"):
            await self._handle_command(text.strip())
            return
        await self.app.send_message(text)

    async def _handle_command(self, cmd: str) -> None:
        parts = cmd.split(None, 1)
        head = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if head == "/leave":
            await self.app.leave_room()
        elif head == "/map":
            await self.app.open_map()
        elif head == "/quit":
            await self.app.action_purge_quit()
        elif head == "/help":
            self.append_multiline(HELP_TEXT.splitlines())
        elif head == "/whoami":
            self.append_system(f"local fingerprint: {self.app.identity_full_fp_or('?')}")
        elif head == "/peers":
            self._render_peers()
        elif head == "/verify":
            self._render_verify(arg)
        elif head == "/trust":
            self._render_trust(arg)
        elif head == "/burn":
            self._handle_burn(arg)
        else:
            self.append_system(f"unknown command: {cmd}", error=True)

    # ---------- /burn ----------

    def _handle_burn(self, arg: str) -> None:
        if not arg:
            if self.burn_seconds is None:
                self.append_system("burn: OFF.  enable with: /burn <seconds 10..86400>")
            else:
                self.append_system(f"burn: ON, {self.burn_seconds}s")
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
        self.append_system(
            f"burn: ON, {n}s — your future messages disappear locally after that. "
            "Best-effort: screenshots, scrollback, and other clients are NOT affected."
        )

    # ---------- peers / verify / trust ----------

    def _render_peers(self) -> None:
        peers = self.app.list_peers()
        if not peers:
            self.append_system("no peers seen in this room yet.")
            return
        self.append_multiline(["peers in this room:"])
        for p in peers:
            status = "TRUSTED" if p["trusted"] else "UNVERIFIED"
            words = " · ".join(p["sas"])
            fp = self._fp_short(p["fp"])
            self.append_system(f"  <{fp}>  {status:11s}  SAS: {words}")

    def _render_verify(self, arg: str) -> None:
        if not arg:
            self.append_system("usage: /verify <fp8>", error=True)
            return
        info = self.app.peer_sas(arg)
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
        ok = self.app.mark_trusted(arg)
        if ok:
            self.append_system(f"peer <{arg}> marked TRUSTED for this session.")
        else:
            self.append_system(f"unknown peer fp: {arg}", error=True)

    def action_noop(self) -> None:
        pass

    # ---------- cleanup ----------

    def purge_local(self) -> None:
        """Called by the app on /leave or /quit — cancel burn tasks and zero buffers."""
        for e in self._lines:
            if e.burn_task is not None and not e.burn_task.done():
                e.burn_task.cancel()
            if e.text_buf is not None:
                for i in range(len(e.text_buf)):
                    e.text_buf[i] = 0
        self._lines.clear()
