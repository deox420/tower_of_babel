"""MIRAGE in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `MirageApp(App)` wrapper that was launched
via `babel mirage`; that wrapper is gone in v2.0.0 — the menu is the
single entry into MIRAGE. The engine still runs as an asyncio task
on the suite's Textual loop and survives backgrounding via Alt+0;
see docs/V2_REDESIGN.md §7.4.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from babel import art, theme
from babel.art import BABEL_TAGLINE
from babel.views import ToolHomeView

from tools.mirage.engine import (
    EngineConfig, Event, HttpxTransport, MirageEngine,
)
from tools.mirage.profile import LOCALES, list_profiles


_PROFILE_NAMES = [s.name for s in list_profiles()]


class MirageView(ToolHomeView):
    """MIRAGE's interactive home view. SERVICE-flavour: survives Alt+0."""

    name: ClassVar[str] = "MIRAGE"
    flavour: ClassVar[str] = "SERVICE"
    logo: ClassVar[str] = art.MIRAGE_LOGO
    summary: ClassVar[str] = (
        "Cover-traffic generator. Real httpx requests over Tor SOCKS5h, "
        "Zipf-weighted per-profile site catalog, hard caps on bandwidth "
        "and request rate."
    )
    cli_examples: ClassVar[list[tuple[str, str]]] = []
    threat_note: ClassVar[str] = ""

    DEFAULT_CSS = f"""
    MirageView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    MirageView .title {{ color: {theme.GREEN}; text-style: bold; }}
    MirageView .tagline {{ color: {theme.CYAN}; text-style: dim italic; }}
    MirageView .status {{ color: {theme.MUTE}; }}
    MirageView .status.warn {{ color: {theme.AMBER}; }}
    MirageView .status.err {{ color: {theme.RED}; }}
    MirageView .field {{ color: {theme.GREEN}; }}
    MirageView .url {{ color: {theme.CYAN}; }}
    """

    BINDINGS = [
        Binding("s", "start",   "start",   show=True),
        Binding("p", "pause",   "pause",   show=True),
        Binding("r", "resume",  "resume",  show=True),
        Binding("o", "honest",  "honest",  show=True),
        Binding("l", "cycle_locale",  "locale",  show=True),
        Binding("f", "cycle_profile", "profile", show=True),
        Binding("t", "toggle_tor", "tor", show=True),
        Binding("plus",   "bw_up",     "bw+", show=False),
        Binding("minus",  "bw_down",   "bw-", show=False),
        Binding("right_square_bracket", "rate_up",   "rate+", show=False),
        Binding("left_square_bracket",  "rate_down", "rate-", show=False),
        Binding("n", "rotate", "newnym", show=True),
        Binding("c", "clear",  "clear",  show=True),
        Binding("escape", "leave", "back", show=True, priority=True),
        Binding("alt+0",  "leave", "menu", show=False, priority=True),
        Binding("q",      "leave", "quit", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.config = EngineConfig()
        self.engine: MirageEngine | None = None
        self._honest = False
        self._mode_line: Static | None = None
        self._status_line: Static | None = None
        self._snapshot_line: Static | None = None
        self._events_widget: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("MIRAGE -- cover traffic generator", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            self._mode_line = Static(self._mode_text(), classes="status")
            yield self._mode_line
            yield Static(" ")
            self._snapshot_line = Static(
                "  (press [s] to start; engine is idle)",
                classes="field",
            )
            yield self._snapshot_line
            yield Static(" ")
            self._events_widget = Static("", classes="status")
            yield self._events_widget
            self._status_line = Static("", classes="status")
            yield self._status_line
            yield Static(" ")
            yield Static(
                "  [s] start  [p] pause  [r] resume  [o] honest  "
                "[f] profile  [l] locale  [t] tor  [n] newnym  "
                "[c] clear  [Esc] back",
                classes="status",
            )

    def on_mount(self) -> None:
        # ToolHomeView's on_mount focuses the widget; keep that and
        # add our 1-second tick for the snapshot panel.
        try:
            self.focus()
        except Exception:
            pass
        self.set_interval(1.0, self._tick)

    # ----- header / refresh ---------------------------------------------

    def _mode_text(self) -> str:
        c = self.config
        net = "tor" if c.use_tor else "CLEARNET"
        honest = "on" if self._honest else "off"
        return (
            f"  profile={c.profile}  locale={c.locale}  net={net}  "
            f"bw<={c.bw_kbps} KB/s  rate<={c.rate_rpm} rpm  "
            f"cpu<={c.cpu_pct}%  honest={honest}"
        )

    def _refresh_mode(self) -> None:
        if self._mode_line is not None:
            self._mode_line.update(self._mode_text())

    def _tick(self) -> None:
        if self.engine is None or self._snapshot_line is None:
            return
        snap = self.engine.snapshot()
        up = float(snap.get("uptime_sec", 0.0))
        kbpm = int((int(snap.get("bytes_in", 0)) / 1024.0) /
                   max(1e-3, up / 60.0))
        rpm = int(int(snap.get("requests", 0)) /
                  max(1e-3, up / 60.0))
        running = bool(snap.get("running"))
        paused = bool(snap.get("paused"))
        if paused:
            state = "paused"
        elif running:
            state = "running"
        else:
            state = "stopped"
        self._snapshot_line.update(
            f"  {state}  {snap['requests']} requests  "
            f"{kbpm} KB/min avg  cpu {snap['cpu_avg']:.1f}%  "
            f"uptime {_fmt_uptime(up)}"
        )
        if self._honest and self._events_widget is not None:
            events = self.engine.events(limit=8)
            lines = [_fmt_event(e) for e in events]
            self._events_widget.update("\n".join(lines))

    # ----- Service Protocol -------------------------------------------

    def status_line(self) -> str:
        if self.engine is None:
            return "idle"
        snap = self.engine.snapshot()
        if snap.get("paused"):
            return "paused"
        if snap.get("running"):
            return f"{snap.get('requests', 0)} req"
        return "stopped"

    def footer_contribution(self) -> dict:
        if self.engine is not None and self.engine.is_running():
            return {"TOR": "on" if self.config.use_tor else ""}
        return {}

    async def purge_local(self) -> None:
        """Stop the engine cleanly on suite quit."""
        if self.engine is not None:
            try:
                await self.engine.stop()
            except Exception:
                pass
            self.engine = None

    # ----- key handlers ------------------------------------------------

    def action_cycle_locale(self) -> None:
        i = (LOCALES.index(self.config.locale) + 1) % len(LOCALES)
        self.config.locale = LOCALES[i]
        self._refresh_mode()

    def action_cycle_profile(self) -> None:
        i = (_PROFILE_NAMES.index(self.config.profile) + 1) % len(_PROFILE_NAMES)
        self.config.profile = _PROFILE_NAMES[i]
        self._refresh_mode()

    def action_toggle_tor(self) -> None:
        if self.config.use_tor:
            self._set_status(
                "clearnet bypass: Tor will NOT be used. press [t] again to revert.",
                "err",
            )
        self.config.use_tor = not self.config.use_tor
        self._refresh_mode()

    def action_honest(self) -> None:
        self._honest = not self._honest
        self.config.honest = self._honest
        if not self._honest and self._events_widget is not None:
            self._events_widget.update("")
        self._refresh_mode()

    def action_clear(self) -> None:
        if self._events_widget is not None:
            self._events_widget.update("")
        if self._status_line is not None:
            self._status_line.update("")

    def action_bw_up(self) -> None:
        self.config.bw_kbps = min(4096, self.config.bw_kbps + 10)
        self._refresh_mode()

    def action_bw_down(self) -> None:
        self.config.bw_kbps = max(1, self.config.bw_kbps - 10)
        self._refresh_mode()

    def action_rate_up(self) -> None:
        self.config.rate_rpm = min(240, self.config.rate_rpm + 5)
        self._refresh_mode()

    def action_rate_down(self) -> None:
        self.config.rate_rpm = max(1, self.config.rate_rpm - 5)
        self._refresh_mode()

    def action_start(self) -> None:
        if self.engine is not None and self.engine.is_running():
            self._set_status("already running", "warn")
            return
        self.run_worker(self._start_engine(), exclusive=True)

    def action_pause(self) -> None:
        if self.engine is None:
            return
        self.engine.pause()
        self._set_status("paused", "warn")

    def action_resume(self) -> None:
        if self.engine is None:
            return
        self.engine.resume()
        self._set_status("resumed", "")

    def action_rotate(self) -> None:
        if self.engine is None:
            return
        self.run_worker(self.engine.rotate_now(), exclusive=False)
        self._set_status("NEWNYM requested", "")

    def action_leave(self) -> None:
        # SERVICE-flavour leave: the chrome will keep this view in the
        # slot (engine stays running). Use Ctrl+W to actually close +
        # purge the engine.
        super().action_leave()

    # ----- workers -----------------------------------------------------

    async def _start_engine(self) -> None:
        try:
            transport = HttpxTransport(use_tor=self.config.use_tor)
        except RuntimeError as e:
            self._set_status(str(e), "err")
            return
        except ImportError:
            self._set_status("httpx not installed -- see `babel --exec mirage --setup`",
                             "err")
            return

        def on_event(_ev: Event) -> None:
            return

        self.engine = MirageEngine(
            config=self.config, transport=transport, on_event=on_event,
        )
        try:
            await self.engine.start()
            self._set_status("engine started", "")
        except RuntimeError as e:
            self._set_status(str(e), "err")

    # ----- helpers -----------------------------------------------------

    def _set_status(self, text: str, cls: str) -> None:
        if self._status_line is None:
            return
        self._status_line.update(text)
        self._status_line.set_classes(f"status {cls}".strip())


def _fmt_uptime(sec: float) -> str:
    if sec < 60:
        return f"{int(sec)}s"
    if sec < 3600:
        return f"{int(sec // 60)}m{int(sec % 60):02d}s"
    return f"{int(sec // 3600)}h{int((sec % 3600) // 60):02d}m"


def _fmt_event(e: Event) -> str:
    ts = datetime.fromtimestamp(e.ts_unix, tz=timezone.utc).strftime("%H:%M:%S")
    if e.error:
        return f"  [{ts}] ERR {e.host}  {e.error}"
    return (
        f"  [{ts}] GET {e.host}  "
        f"{e.bytes_in / 1024:5.1f} KB  {e.duration_ms:5.0f} ms  "
        f"({e.status})"
    )


__all__ = ["MirageView"]
