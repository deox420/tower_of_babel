"""MIRAGE Textual screen.

The screen is the foreground view of MIRAGE -- the user lands here
from the babel menu (``[5]``) and can:

  * pick a profile / locale / Tor toggle
  * start, pause, resume, stop the engine
  * watch the live event ring buffer if honest mode is on
  * request a one-shot NEWNYM
  * close the slot, which purges the engine

The engine itself runs as an asyncio task on the Textual loop; the
screen wakes once per second to refresh the snapshot panel.  Real
work happens in ``tools.mirage.engine``; this module is presentation
only and would ideally have no business logic at all.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Static

from babel import theme
from babel.art import BABEL_TAGLINE

from tools.mirage.engine import (
    EngineConfig, Event, HttpxTransport, MirageEngine,
)
from tools.mirage.profile import LOCALES, list_profiles


_PROFILE_NAMES = [s.name for s in list_profiles()]


class MirageView(Container):
    """Cover-traffic generator.  Real httpx requests, hard rate caps.

    Mounted inside the babel chrome's content slot.  Service-flavoured:
    the view stays alive when the user backgrounds it (Alt+0), occupies
    one numbered slot in the chrome's ``ServiceRegistry``, and feeds
    the chrome's footer aggregate (TOR indicator when Tor is on).

    The Service Protocol is implemented by a separate ``_MirageBoundService``
    instance assigned to ``self.service`` -- the chrome's registry holds
    the Service, not the widget, so pentest can drive the protocol
    without importing Textual (docs/ARCHITECTURE.md decision log
    2026-05-19).
    """

    name = "MIRAGE"
    flavour = "SERVICE"
    can_focus = True

    DEFAULT_CSS = f"""
    MirageView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
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
        Binding("escape", "leave", "back", show=True),
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
        # Service protocol -- a plain Python adapter the chrome's
        # registry holds.  The engine is None until [s], so its
        # status_line / footer_contribution report idle until then.
        self.service = _MirageBoundService(self)

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
        # Tick once per second to refresh the snapshot + honest panel.
        self.set_interval(1.0, self._tick)

    # ----- header / refresh ------------------------------------------------

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

    # ----- key handlers ----------------------------------------------------

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
        # In-chrome path: hand back to the menu.  Engine keeps
        # running -- the slot stays live in the registry.  Ctrl+W
        # (or chrome's quit handler) is what calls purge_local().
        leave = getattr(self.app, "leave_tool", None)
        if callable(leave):
            leave(self)
            return
        # Standalone MirageApp path (`babel mirage start`): drain
        # the engine then exit the app.
        if self.engine is not None:
            self.run_worker(self._purge_then_exit(), exclusive=True)
        else:
            self.app.exit()

    # ----- workers ---------------------------------------------------------

    async def _start_engine(self) -> None:
        try:
            transport = HttpxTransport(use_tor=self.config.use_tor)
        except RuntimeError as e:
            self._set_status(str(e), "err")
            return
        except ImportError:
            self._set_status("httpx not installed -- see `babel mirage --setup`", "err")
            return

        def on_event(_ev: Event) -> None:
            # Snapshot panel refreshes on its 1s tick; we only need to
            # nudge the event widget when honest mode is on, and the
            # tick will pick that up too.
            return

        self.engine = MirageEngine(
            config=self.config, transport=transport, on_event=on_event,
        )
        try:
            await self.engine.start()
            self._set_status("engine started", "")
        except RuntimeError as e:
            self._set_status(str(e), "err")

    async def _purge_then_exit(self) -> None:
        if self.engine is not None:
            await self.engine.stop()
            self.engine = None
        self.app.exit()

    # ----- helpers ---------------------------------------------------------

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


class _MirageBoundService:
    """Service-protocol adapter bound to a live ``MirageView``.

    The view ``self.engine`` is None until the user presses ``[s]``;
    until then the service reports idle.  ``purge_local`` stops the
    engine (cooperative, <1s) and clears the view's reference so a
    later Alt+N to this slot starts clean.

    Kept inline in this module (not in ``service.py``) so the view
    and its service share lifetime + state by construction.
    """

    name = "MIRAGE"

    def __init__(self, view: "MirageView") -> None:
        self.view = view
        self._purged = False

    def _eng(self) -> "MirageEngine | None":
        return getattr(self.view, "engine", None)

    def status_line(self) -> str:
        eng = self._eng()
        if eng is None or not eng.is_running():
            return "idle"
        snap = eng.snapshot()
        up = max(1.0, float(snap.get("uptime_sec", 1.0)))
        reqs = int(snap.get("requests", 0))
        bytes_in = int(snap.get("bytes_in", 0))
        kbpm = int((bytes_in / 1024.0) / (up / 60.0))
        rpm = int(reqs / (up / 60.0))
        if snap.get("paused"):
            return f"paused {reqs} reqs"
        return f"{rpm} rpm {kbpm} KB/min"

    def footer_contribution(self) -> dict[str, str]:
        eng = self._eng()
        if eng is None or not eng.is_running():
            return {}
        contrib: dict[str, str] = {}
        if getattr(eng.config, "use_tor", False):
            contrib["TOR"] = "on"
        return contrib

    async def purge_local(self) -> None:
        if self._purged:
            return
        eng = self._eng()
        if eng is not None:
            try:
                await asyncio.wait_for(eng.stop(), timeout=0.95)
            except (asyncio.TimeoutError, Exception):
                pass
        try:
            self.view.engine = None
        except Exception:
            pass
        self._purged = True

    def resource_caps(self) -> dict[str, float]:
        cfg = self.view.config
        return {
            "bandwidth_kbps": float(cfg.bw_kbps),
            "rate_rpm":       float(cfg.rate_rpm),
            "cpu_pct":        float(cfg.cpu_pct),
        }


class MirageApp(App):
    TITLE = "TOWER OF BABEL / MIRAGE"
    BINDINGS = [
        Binding("ctrl+c", "quit", "quit", show=False, priority=True),
        Binding("ctrl+q", "quit", "quit", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield MirageView()
        yield Footer()


def run() -> None:
    MirageApp().run()


__all__ = ["MirageView", "MirageApp", "run"]
