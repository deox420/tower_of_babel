"""Babel suite chrome -- Phase 1.

Implements MASTER.md Section 4.2 (the persistent outer frame), 4.4
(the multiplex model with slot bar, service registry, and global
hotkeys), and 6 (the main-menu hand-off).

Shape::

    +----------------------------- TOWER OF BABEL ---------- v1.0.0 -+
    | [1:VOID 2 peers]  [2:MIRAGE 12 KB/s]                           |  <- header (slot bar)
    |                                                                 |
    |   <view content mounts here (menu, tool home, etc.)>            |  <- content slot
    |                                                                 |
    |--- TOR *  --- MEM *  --- CRYPTO .  --- SWAP *  --- 14:32:09 ---|  <- footer
    +----------------------------------------------------------------+

The frame is drawn once.  Views (the menu, tool home screens) mount
and unmount in the content slot; the chrome never repaints, the
indicators tick on their own timers.

For Phase 1, the menu remains the only built-in view; VOID itself
still launches as its own ``VoidApp`` via the Phase-0 return-value
hand-off (see ``babel.__main__``).  The slot model is therefore
exercised by mock services in ``pentest/babel/`` -- the prompt
explicitly says ``VOID + future MIRAGE slot simulation``.  Wiring
VOID's real chat state into the chrome is downstream work.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Protocol, runtime_checkable


def _now() -> float:
    """Wall-clock monotonic seconds.  Cheap; called by every tick."""
    return time.monotonic()

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static

from babel import theme
from shared.crypto.secure_mem import mlock_status, swap_active
from shared.tor.socks_detect import detect_socks_port


SUITE_NAME = "TOWER OF BABEL"

# Default slot cap (MASTER.md 4.4).  Override with ``BABEL_MAX_SERVICES``.
DEFAULT_MAX_SERVICES = 4


def _max_services() -> int:
    raw = os.environ.get("BABEL_MAX_SERVICES")
    if not raw:
        return DEFAULT_MAX_SERVICES
    try:
        n = int(raw)
    except ValueError:
        return DEFAULT_MAX_SERVICES
    return max(1, n)


# ---------------------------------------------------------------------------
# Service contract (MASTER.md 4.4 "Resource contract").
# ---------------------------------------------------------------------------

@runtime_checkable
class Service(Protocol):
    """Anything that wants a slot in the chrome implements this.

    Phase 1 only uses ``status_line``, ``footer_contribution`` and
    ``purge_local``; ``resource_caps`` is read by the suite-level
    ``babel --setup`` diagnostic (Phase 5+).  The Protocol is
    runtime-checkable so the registry can defensively probe a
    half-built service in tests.
    """

    name: str

    def status_line(self) -> str: ...

    def footer_contribution(self) -> dict[str, str]: ...

    async def purge_local(self) -> None: ...

    def resource_caps(self) -> dict[str, float]: ...


@dataclass
class _Slot:
    index: int
    service: Service


class ServiceRegistry:
    """Holds the active service set + the slot ordering.

    The chrome consults the registry once per render to build the
    slot bar and to aggregate footer state.  Hotkey handlers in
    ``ChromeApp`` mutate it.
    """

    def __init__(self, max_services: int | None = None) -> None:
        self.max_services = max_services if max_services is not None else _max_services()
        self._slots: dict[int, _Slot] = {}
        self._warn_caps: set[str] = set()   # service names that flagged a swap+mlock issue

    # ----- inspection -------------------------------------------------------

    def __len__(self) -> int:
        return len(self._slots)

    def slots(self) -> list[_Slot]:
        return [self._slots[k] for k in sorted(self._slots)]

    def is_full(self) -> bool:
        return len(self._slots) >= self.max_services

    def by_index(self, index: int) -> Service | None:
        slot = self._slots.get(index)
        return slot.service if slot is not None else None

    def by_name(self, name: str) -> tuple[int, Service] | None:
        for idx, slot in self._slots.items():
            if slot.service.name == name:
                return idx, slot.service
        return None

    # ----- mutation ---------------------------------------------------------

    def register(self, service: Service) -> int:
        """Insert ``service`` in the lowest free slot.  Raises if full."""
        if self.is_full():
            raise RuntimeError(
                f"babel: service slot limit ({self.max_services}) reached"
            )
        if self.by_name(service.name) is not None:
            raise RuntimeError(f"babel: service {service.name!r} already registered")
        for i in range(1, self.max_services + 1):
            if i not in self._slots:
                self._slots[i] = _Slot(index=i, service=service)
                return i
        # Unreachable given is_full() above.
        raise RuntimeError("babel: no free slot")

    async def close(self, index: int) -> bool:
        """Purge + remove the service at ``index``.  Returns True on close."""
        slot = self._slots.pop(index, None)
        if slot is None:
            return False
        try:
            await asyncio.wait_for(slot.service.purge_local(), timeout=1.0)
        except (asyncio.TimeoutError, Exception):
            # Cooperative contract is "under 1 second".  If a service
            # misbehaves we drop the reference and move on; Python GC and
            # SecureBytes destructors mop up.
            pass
        return True

    async def close_all(self) -> None:
        """Called on ChromeApp quit.  Purges every live service in parallel.

        MASTER.md 4.4 ``purge_local()`` test: zeros every buffer across
        every service in under 4 seconds total.  Parallel close keeps
        that budget even with a full slot table.
        """
        slots = list(self._slots.values())
        self._slots.clear()
        async def _one(s: _Slot) -> None:
            try:
                await asyncio.wait_for(s.service.purge_local(), timeout=1.0)
            except (asyncio.TimeoutError, Exception):
                pass
        await asyncio.gather(*[_one(s) for s in slots], return_exceptions=True)

    # ----- footer aggregation ----------------------------------------------

    def aggregate_footer(self) -> dict[str, tuple[str, str]]:
        """Merge each service's ``footer_contribution()`` into the suite footer.

        Each indicator answers with ``(state, label)``.  The base layer
        (the probes below) decides the default; a service can upgrade
        a probe to ``"on"`` or downgrade it to ``"warn"`` via its dict.
        """
        agg: dict[str, tuple[str, str]] = {}
        tor_users = 0
        mem_count = 0
        crypto_users = 0
        swap_warn = False
        for slot in self._slots.values():
            try:
                contrib = slot.service.footer_contribution() or {}
            except Exception:
                continue
            if contrib.get("TOR") == "on":
                tor_users += 1
            if contrib.get("MEM") == "on":
                mem_count += int(contrib.get("MEM_COUNT", 1) or 1)
            if contrib.get("CRYPTO") == "on":
                crypto_users += 1
            if contrib.get("SWAP") == "warn":
                swap_warn = True
        if tor_users:
            agg["TOR"] = ("on", f"TOR {tor_users} svcs" if tor_users > 1 else "TOR on")
        if mem_count:
            agg["MEM"] = ("on", f"MEM {mem_count} buf")
        if crypto_users:
            agg["CRYPTO"] = ("on", "CRYPTO live")
        if swap_warn:
            agg["SWAP"] = ("warn", "SWAP risk")
        return agg


# ---------------------------------------------------------------------------
# Footer indicator probes (real, not decorative -- MASTER.md 3.1).
# Each returns ``(state, label)`` where ``state`` is one of
# "on" / "off" / "pending" / "warn" / "error".
# ---------------------------------------------------------------------------

def _tor_probe() -> tuple[str, str]:
    port = detect_socks_port(timeout=0.5)
    if port is None:
        return ("off", "TOR off")
    return ("on", f"TOR :{port}")


def _mem_probe() -> tuple[str, str]:
    st = mlock_status()
    if st["mlock_ok"]:
        return ("on", "MEM mlock")
    return ("warn", f"MEM {st.get('reason') or 'no mlock'}")


def _crypto_probe() -> tuple[str, str]:
    # Baseline reports "off" / no live key material.  The registry layer
    # upgrades this when any service is holding keys.
    return ("off", "CRYPTO idle")


def _swap_probe() -> tuple[str, str]:
    if swap_active():
        st = mlock_status()
        if not st["mlock_ok"]:
            return ("warn", "SWAP risk")
        return ("on", "SWAP+lock")
    return ("on", "SWAP off")


def _clock_probe() -> tuple[str, str]:
    # datetime.utcnow() is deprecated in Python 3.12+; use a tz-aware
    # `now(UTC)` and format the wall-clock components for the footer.
    now = datetime.datetime.now(datetime.timezone.utc)
    return ("on", now.strftime("%H:%M:%S UTC"))


footer_callables: dict[str, Callable[[], tuple[str, str]]] = {
    "TOR":    _tor_probe,
    "MEM":    _mem_probe,
    "CRYPTO": _crypto_probe,
    "SWAP":   _swap_probe,
    "CLOCK":  _clock_probe,
}


# ---------------------------------------------------------------------------
# Rendering helpers.
# ---------------------------------------------------------------------------

def _state_glyph(state: str) -> str:
    return {
        "on":      theme.glyph("active"),
        "off":     theme.glyph("off"),
        "pending": theme.glyph("pending"),
        "warn":    theme.glyph("warn"),
        "error":   theme.glyph("error"),
    }.get(state, theme.glyph("off"))


def render_slot_bar(registry: ServiceRegistry, compact: bool) -> str:
    """One line of badges for the active services.

    Compact mode strips the human label and just shows ``[N:NAME]``.
    """
    if not len(registry):
        # Tagline lives here when no service occupies a slot -- the chrome
        # always has something to say.
        return f"  // {theme.glyph('em')} confusion of tongues, by design {theme.glyph('em')}"
    parts: list[str] = []
    for slot in registry.slots():
        if compact:
            parts.append(f"[{slot.index}:{slot.service.name}]")
        else:
            try:
                line = slot.service.status_line()
            except Exception:
                line = "?"
            parts.append(f"[{slot.index}:{slot.service.name} {line}]")
    return "  ".join(parts)


def render_footer(
    aggregated: dict[str, tuple[str, str]] | None = None,
    compact: bool | None = None,
) -> str:
    """The five-indicator strip.

    ``aggregated`` -- per-indicator overrides from ServiceRegistry; the
    bare probes win otherwise.  ``compact`` -- when True, label
    collapses to one letter per indicator (Termux portrait, MASTER.md
    3.5 layout rule #2).
    """
    if compact is None:
        compact = theme.is_compact()
    parts: list[str] = []
    order = ("TOR", "MEM", "CRYPTO", "SWAP", "CLOCK")
    for name in order:
        if aggregated and name in aggregated:
            state, label = aggregated[name]
        else:
            try:
                state, label = footer_callables[name]()
            except Exception:
                state, label = ("error", f"{name} ?")
        g = _state_glyph(state)
        if name == "CLOCK":
            parts.append(label)  # the timestamp speaks for itself
        elif compact:
            short = {"TOR": "T", "MEM": "M", "CRYPTO": "C", "SWAP": "S"}[name]
            parts.append(f"{short}{g}")
        else:
            # ``label`` already starts with the indicator name when it
            # comes from one of the bare probes; aggregated overrides
            # may carry richer text (``TOR 3 svcs``) -- show it verbatim.
            parts.append(f"{g} {label}")
    sep = f" {theme.glyph('em')}{theme.glyph('em')} "
    return sep.join(parts)


# ---------------------------------------------------------------------------
# Chrome -- the single visible Screen.
# ---------------------------------------------------------------------------

class _HeaderBar(Static):
    """Slot bar + suite title + version.  One line tall."""


class _ContentSlot(Container):
    """Where views (menu, tool homes) mount.  No border of its own."""


class _HintsBar(Static):
    """Context-sensitive hotkey hints, one line tall.

    Lives directly above the footer of indicators.  Updated on
    every navigation event so the user always sees the keys that
    are wired to the view currently in focus.
    """


class _FooterBar(Static):
    """Aggregated TOR / MEM / CRYPTO / SWAP / CLOCK strip."""


class Chrome(Screen):
    """The persistent suite shell.

    Implementation note: we deliberately do NOT use Textual's
    ``push_screen`` for tool views -- pushing a new screen would hide
    Chrome.  Instead the content slot is a plain container we mount
    children into via ``push_view`` / ``pop_view``.  The frame draws
    once at mount and only repaints on terminal resize.
    """

    DEFAULT_CSS = f"""
    Chrome {{
        background: {theme.BG};
        color: {theme.GREEN};
        layout: vertical;
        border: round {theme.GREEN} 55%;
        padding: 0 1;
    }}
    _HeaderBar {{
        height: 1;
        background: {theme.BG};
        color: {theme.CYAN};
        padding: 0 1;
        border-bottom: solid {theme.GREEN} 30%;
    }}
    _ContentSlot {{
        height: 1fr;
        background: {theme.BG};
    }}
    _HintsBar {{
        height: 1;
        background: {theme.BG};
        color: {theme.MUTE};
        text-style: dim;
        padding: 0 1;
        border-top: solid {theme.GREEN} 30%;
    }}
    _FooterBar {{
        height: 1;
        background: {theme.BG};
        color: {theme.CYAN};
        padding: 0 1;
    }}
    """

    BINDINGS: list[Binding] = []   # ChromeApp owns the global hotkeys.

    def __init__(
        self,
        version: str,
        registry: ServiceRegistry,
        initial_view: Widget | None = None,
    ) -> None:
        super().__init__()
        self.version = version
        self.registry = registry
        self._view_stack: list[Widget] = []
        self._pending_initial = initial_view
        # Flash status used by docs/NAVIGATION.md section 5 (e.g.
        # "MASK closed -- opening STRIP") and section 9 (the
        # multiplex-hotkey nudge during the first 5 seconds on the
        # menu).  Empty string means "fall back to the per-view
        # hints"; ``_flash_until`` is a wall-clock deadline.
        self._flash_text: str = ""
        self._flash_until: float = 0.0
        self._session_started_at: float = 0.0

    # ----- composition ------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield _HeaderBar(self._header_text(), id="babel-header")
        yield _ContentSlot(id="babel-slot")
        yield _HintsBar(self._hints_text(), id="babel-hints")
        yield _FooterBar(self._footer_text(), id="babel-footer")

    def on_mount(self) -> None:
        # Tick the clock and footer probes once per second.
        self.set_interval(1.0, self._tick)
        # Defensive: register a one-shot refresh after layout so the
        # initial frame is correct on very small terminals (Termux).
        self.call_after_refresh(self._tick)
        self._session_started_at = _now()
        if self._pending_initial is not None:
            view, self._pending_initial = self._pending_initial, None
            self.push_view(view)

    # ----- flash status (NAVIGATION.md section 5 + 9) ----------------------

    def flash(self, text: str, seconds: float = 4.0) -> None:
        """Show ``text`` in the hints line for ``seconds`` then revert.

        Used for transient messages like
        ``"MASK closed -- opening STRIP"`` and the slots-full warning.
        Suppressed when ``text`` is empty.
        """
        self._flash_text = text
        self._flash_until = _now() + max(0.0, seconds)
        self._tick()

    def _flash_active(self) -> bool:
        return bool(self._flash_text) and _now() < self._flash_until

    def _boot_nudge_active(self) -> bool:
        """Hint-bar nudge for the multiplex hotkeys.

        Per docs/NAVIGATION.md section 9: shown on the menu for the
        first 5 seconds after session start, suppressed on the
        Termux 60-col floor.
        """
        if theme.is_very_compact():
            return False
        if self._session_started_at == 0.0:
            return False
        if _now() - self._session_started_at >= 5.0:
            return False
        visible = self.current_visible()
        return type(visible).__name__ == "MainMenuView" if visible else False

    # ----- view stack -------------------------------------------------------

    def push_view(self, view: Widget) -> None:
        """Mount ``view`` in the content slot, hiding any current view."""
        slot = self.query_one("#babel-slot", _ContentSlot)
        if self._view_stack:
            self._view_stack[-1].display = False
        self._view_stack.append(view)
        slot.mount(view)

    def pop_view(self) -> Widget | None:
        """Remove the top view; reveal the one beneath.  Returns the popped widget."""
        if not self._view_stack:
            return None
        top = self._view_stack.pop()
        try:
            top.remove()
        except Exception:
            pass
        if self._view_stack:
            self._view_stack[-1].display = True
        return top

    def replace_view(self, view: Widget) -> None:
        """Equivalent to pop_view() then push_view(view) but cheaper."""
        if self._view_stack:
            self.pop_view()
        self.push_view(view)

    def show_existing(self, view: Widget) -> bool:
        """Make ``view`` (which must already be mounted) the visible one.

        Used by the multiplex model: when a SERVICE-flavour tool gets
        backgrounded (Alt+0) we *hide* its view without removing it,
        so a later Alt+N can re-show it instantly with state intact.

        Returns True if the view was found in the stack.
        """
        if view not in self._view_stack:
            return False
        for v in self._view_stack:
            v.display = (v is view)
        return True

    def current_visible(self) -> Widget | None:
        """The view currently displayed (highest display=True in stack)."""
        for v in reversed(self._view_stack):
            try:
                if v.display:
                    return v
            except Exception:
                continue
        return None

    # ----- header / footer text --------------------------------------------

    def _is_compact(self) -> bool:
        """True if the rendered chrome is narrower than COMPACT_THRESHOLD.

        Prefer Textual's reported size so an on-screen resize event
        flips compact mode immediately; fall back to the OS terminal
        size for the very first render before Textual has settled.
        """
        try:
            w = self.size.width
            if w > 0:
                return w < theme.COMPACT_THRESHOLD
        except Exception:
            pass
        return theme.is_compact()

    def _header_text(self) -> str:
        compact = self._is_compact()
        slots = render_slot_bar(self.registry, compact)
        version = f"v{self.version}"
        if compact:
            return f"{SUITE_NAME}  {version}  {slots}"
        return f"{SUITE_NAME}    {slots}    {version}"

    def _footer_text(self) -> str:
        agg = self.registry.aggregate_footer()
        return render_footer(agg, compact=self._is_compact())

    def _hints_text(self) -> str:
        """Context-sensitive hotkey strip.  Reflects the visible view.

        Order of precedence (high -> low):

        1. ``flash`` -- transient status set via ``Chrome.flash``
           ("MASK closed -- opening STRIP", "slots full ...", etc.).
        2. boot nudge -- the 5-second "<Alt+1..4> jump  <Ctrl+W> close"
           line on the menu only (NAVIGATION.md section 9).
        3. per-view hints based on the visible view's flavour.

        Square brackets are Rich markup delimiters; we use angle
        brackets in hint strings so a stray ``[Alt+]]`` doesn't get
        eaten by the widget's markup parser.
        """
        if self._flash_active():
            return self._flash_text
        compact = self._is_compact()
        visible = self.current_visible()
        cls_name = type(visible).__name__ if visible is not None else ""
        flavour = getattr(visible, "flavour", None)
        if cls_name == "MainMenuView" and self._boot_nudge_active():
            return "<Alt+1..4> jump   <Alt+0> menu   <Ctrl+W> close   <F1> help"

        # Helper: wrap a key in angle brackets.  Square brackets are
        # Rich markup delimiters and trying to render `[Alt+]]` ends up
        # showing the dangling `]` as text; `<key>` sidesteps all of
        # that and is the common terminal-app convention anyway.
        def k(key: str) -> str:
            return f"<{key}>"

        sep = "  " if compact else "   "

        if cls_name == "MainMenuView":
            if compact:
                parts = [f"{k('1-5')} tool",
                         f"{k('q')} quit",
                         f"{k('Ctrl+C')} exit"]
            else:
                parts = [
                    f"{k('1')} VOID", f"{k('2')} MASK", f"{k('3')} STRIP",
                    f"{k('4')} CARRIER", f"{k('5')} MIRAGE",
                    f"{k('q')} quit", f"{k('Ctrl+C')} exit",
                ]
            return sep.join(parts)

        if flavour == "SERVICE":
            slot_hint = (f"{k('Alt+1..N')} slot" if len(self.registry) > 1
                         else f"{k('Alt+0')} menu")
            if compact:
                parts = [f"{k('Esc')} menu",
                         slot_hint,
                         f"{k('Ctrl+W')} close"]
            else:
                parts = [
                    f"{k('Esc')} back to menu",
                    f"{k('Alt+0')} background",
                    f"{k('Alt+1..N')} jump to slot",
                    f"{k('Alt+]')} / {k('Alt+[')} cycle services",
                    f"{k('Ctrl+W')} close service",
                    f"{k('Ctrl+C')} quit",
                ]
            return sep.join(parts)

        if flavour == "ACTION":
            if compact:
                parts = [f"{k('Esc')} menu", f"{k('Ctrl+C')} exit"]
            else:
                parts = [f"{k('Esc')} back to menu",
                         f"{k('Ctrl+C')} quit suite"]
            return sep.join(parts)

        # Unknown view (or boot): keep the line non-empty so the
        # border below stays anchored.
        return f"{k('Ctrl+C')} quit"

    def _tick(self) -> None:
        # Drop expired flash text so the next tick reverts to per-view
        # hints without an explicit caller.
        if self._flash_text and _now() >= self._flash_until:
            self._flash_text = ""
        try:
            self.query_one("#babel-header", _HeaderBar).update(self._header_text())
            self.query_one("#babel-hints",  _HintsBar).update(self._hints_text())
            self.query_one("#babel-footer", _FooterBar).update(self._footer_text())
        except Exception:
            # Chrome may be mid-teardown; swallow.
            pass

    # ----- resize-driven repaint -------------------------------------------

    def on_resize(self) -> None:
        # The compact threshold may have changed; force a header/footer redraw.
        self._tick()


# ---------------------------------------------------------------------------
# ChromeApp -- owns the Chrome screen, the registry, and the global hotkeys.
# ---------------------------------------------------------------------------

class ChromeApp(App):
    """Suite-wide Textual App.

    The App composes exactly one screen, ``Chrome``.  Tool views mount
    inside Chrome's content slot via ``chrome.push_view(...)``.
    """

    TITLE = SUITE_NAME
    SUB_TITLE = "confusion of tongues, by design"

    # Global hotkeys (MASTER.md 4.4, docs/NAVIGATION.md section 2.1).
    #
    # Slot routing:
    #   Alt+1..Alt+9    jump to SERVICE in slot N (no-op if empty)
    #   Alt+0           return to menu (services keep running)
    #   Alt+]/Alt+[     cycle next / previous SERVICE
    #
    # Suite overlays:
    #   F1, Alt+H       help overlay (HelpOverlay)
    #   Alt+M           slot switcher overlay (SlotSwitcherOverlay)
    #
    # New-instance:
    #   Shift+1..5 OR the corresponding symbol-row characters
    #   (!@#$%) -- needed on F-Droid Termux where Shift+digit may
    #   not propagate.  Both shapes route to action_enter_tool_new.
    #
    # Termination:
    #   Ctrl+W          close current SERVICE (calls purge_local)
    #   Ctrl+C, Ctrl+Q  quit suite (purge_local on every SERVICE)
    BINDINGS = [
        Binding("alt+0", "menu_jump", "menu",      priority=True, show=False),
        Binding("alt+1", "slot_jump(1)", "slot 1", priority=True, show=False),
        Binding("alt+2", "slot_jump(2)", "slot 2", priority=True, show=False),
        Binding("alt+3", "slot_jump(3)", "slot 3", priority=True, show=False),
        Binding("alt+4", "slot_jump(4)", "slot 4", priority=True, show=False),
        Binding("alt+5", "slot_jump(5)", "slot 5", priority=True, show=False),
        Binding("alt+6", "slot_jump(6)", "slot 6", priority=True, show=False),
        Binding("alt+7", "slot_jump(7)", "slot 7", priority=True, show=False),
        Binding("alt+8", "slot_jump(8)", "slot 8", priority=True, show=False),
        Binding("alt+9", "slot_jump(9)", "slot 9", priority=True, show=False),
        Binding("alt+m", "slot_switcher", "switch", priority=True, show=False),
        Binding("alt+]", "cycle_next", "next",     priority=True, show=False),
        Binding("alt+[", "cycle_prev", "prev",     priority=True, show=False),
        # Help overlay
        Binding("f1",     "help_overlay", "help", priority=True, show=False),
        Binding("alt+h",  "help_overlay", "help", priority=True, show=False),
        # Shift+digit -> new instance.  Textual's modifier syntax for
        # the digit row is "shift+1" etc.  Symbol-row fallbacks (!,
        # @, #, $, %) cover the F-Droid Termux case where Shift+digit
        # is not reachable from the soft keyboard.
        Binding("shift+1",          "new_tool(1)", "new VOID",   priority=True, show=False),
        Binding("shift+2",          "new_tool(2)", "new MASK",   priority=True, show=False),
        Binding("shift+3",          "new_tool(3)", "new STRIP",  priority=True, show=False),
        Binding("shift+4",          "new_tool(4)", "new CARRIER",priority=True, show=False),
        Binding("shift+5",          "new_tool(5)", "new MIRAGE", priority=True, show=False),
        Binding("exclamation_mark", "new_tool(1)", "new VOID",   priority=True, show=False),
        Binding("at",               "new_tool(2)", "new MASK",   priority=True, show=False),
        Binding("number_sign",      "new_tool(3)", "new STRIP",  priority=True, show=False),
        Binding("dollar_sign",      "new_tool(4)", "new CARRIER",priority=True, show=False),
        Binding("percent_sign",     "new_tool(5)", "new MIRAGE", priority=True, show=False),
        Binding("ctrl+w", "close_service", "close service",
                priority=True, show=False),
        Binding("ctrl+c", "purge_quit", "quit",    priority=True, show=False),
        Binding("ctrl+q", "purge_quit", "quit",    priority=True, show=False),
    ]

    def __init__(
        self,
        initial_view: Widget | None = None,
        version: str = "1.0.0",
        registry: ServiceRegistry | None = None,
    ) -> None:
        super().__init__()
        self.version = version
        self.registry = registry or ServiceRegistry()
        self._initial_view = initial_view
        self.chrome: Chrome | None = None
        # Set by VoidView when the lobby submits and we need to hand
        # off to the legacy VoidApp post-exit (Phase 7 v1.0 bridge).
        self._void_session_args: dict | None = None

    def compose(self) -> ComposeResult:
        # No top-level widgets -- the App's only Screen is Chrome, pushed
        # in on_mount once we know what view (if any) it should host.
        return iter(())

    def on_mount(self) -> None:
        theme.detect_ascii_fallback()
        self.chrome = Chrome(
            version=self.version,
            registry=self.registry,
            initial_view=self._initial_view,
        )
        self.push_screen(self.chrome)

    # ----- view helpers (used by tools) ------------------------------------

    def push_view(self, view: Widget) -> None:
        if self.chrome is not None:
            self.chrome.push_view(view)

    def pop_view(self) -> Widget | None:
        if self.chrome is None:
            return None
        return self.chrome.pop_view()

    def _refresh_chrome(self) -> None:
        """Trigger an immediate header/hints/footer repaint.

        The 1-second tick already updates these, but waiting up to a
        second after each navigation makes the hints bar feel
        sluggish.  Called from enter_tool / leave_tool /
        return_to_menu / slot_jump.
        """
        if self.chrome is not None:
            self.chrome._tick()

    def enter_tool(
        self, name: str, *, new_instance: bool = False,
        prefill: dict | None = None,
    ) -> None:
        """Mount the chosen tool's view inside the chrome.

        Multiplex semantics (MASTER.md 4.4, NAVIGATION.md section 4
        + 5):

        * SERVICE-flavour tools (VOID, MIRAGE) keep one numbered slot
          per live instance.  Default re-entry focuses an existing
          slot of the same name (no second instance, state intact).
          Pass ``new_instance=True`` to force a fresh slot
          (Shift+digit / symbol-row).
        * ACTION-flavour tools (MASK, STRIP, CARRIER) are foreground
          only.  Opening one tears down any currently-mounted ACTION
          view first; a flash status announces the swap.

        ``prefill`` is an optional dict the caller (typically the
        menu's paste field) hands to ``view.prefill_invite`` /
        ``prefill_link`` once mounted.
        """
        if self.chrome is None:
            return
        from babel.views import view_class_for

        cls = view_class_for(name)
        if cls is None:
            return
        flavour = getattr(cls, "flavour", "ACTION")
        cls_name = getattr(cls, "name", name.upper())

        # SERVICE: focus existing slot unless the caller asked for
        # a new instance.
        if flavour == "SERVICE" and not new_instance:
            existing = self.registry.by_name(cls_name)
            if existing is not None:
                _idx, svc = existing
                view = getattr(svc, "view", None)
                if view is not None:
                    self.chrome.show_existing(view)
                    try:
                        view.focus()
                    except Exception:
                        pass
                    self._apply_prefill(view, name, prefill)
                    self._refresh_chrome()
                    return

        # ACTION: at most one foreground at a time.  Tear down any
        # existing ACTION view first and announce the swap.
        if flavour == "ACTION":
            displaced = self._unmount_existing_action()
            if displaced is not None:
                self.chrome.flash(
                    f"{displaced.upper()} closed -- opening {cls_name}"
                )

        view = cls()
        if flavour == "SERVICE":
            svc = getattr(view, "service", None)
            if svc is not None:
                try:
                    self.registry.register(svc)
                except RuntimeError:
                    # Slot limit hit -- announce and bail before we
                    # mount a view we can't track.
                    self.chrome.flash(
                        f"slots full ({self.registry.max_services}) "
                        f"-- close one with Ctrl+W"
                    )
                    try:
                        view.remove()
                    except Exception:
                        pass
                    self._refresh_chrome()
                    return

        self.chrome.push_view(view)
        self._apply_prefill(view, name, prefill)
        self._refresh_chrome()

    def _unmount_existing_action(self) -> str | None:
        """Tear down the currently-mounted ACTION view (if any).

        Returns the name attribute of the displaced view, or None.
        """
        if self.chrome is None:
            return None
        for v in list(self.chrome._view_stack):
            if getattr(v, "flavour", None) == "ACTION":
                displaced_name = getattr(v, "name", type(v).__name__)
                self.chrome._view_stack.remove(v)
                try:
                    v.remove()
                except Exception:
                    pass
                return displaced_name
        return None

    def _apply_prefill(
        self, view: Widget, tool: str, prefill: dict | None,
    ) -> None:
        """If ``prefill`` carries a link / data, hand it to the view."""
        if not prefill:
            return
        link = prefill.get("link")
        if not link:
            return
        if tool == "void":
            fn = getattr(view, "prefill_invite", None)
        else:
            fn = getattr(view, "prefill_link", None)
        if callable(fn):
            try:
                fn(link)
            except Exception:
                pass

    def leave_tool(self, view: Widget) -> None:
        """Tool view asks to be backgrounded / torn down.

        Called from a view's Esc / Alt+0 binding.

        SERVICE views: hidden but stay mounted; the registry slot
        stays live so Alt+N comes back to the same state.

        ACTION views: removed from the DOM + view stack entirely.
        """
        if self.chrome is None:
            return
        flavour = getattr(view, "flavour", "ACTION")
        if flavour == "ACTION":
            if view in self.chrome._view_stack:
                self.chrome._view_stack.remove(view)
            try:
                view.remove()
            except Exception:
                pass
        self.return_to_menu()
        self._refresh_chrome()

    def return_to_menu(self) -> None:
        """Reveal the menu view; keep any backgrounded services alive."""
        if self.chrome is None:
            return
        for v in self.chrome._view_stack:
            # MainMenuView is the only non-ToolHomeView that lives in
            # the stack (Phase 1).  Match by class name to avoid an
            # import cycle with babel.menu.
            if type(v).__name__ == "MainMenuView":
                self.chrome.show_existing(v)
                try:
                    v.focus()
                except Exception:
                    pass
                return
        # No menu in the stack -- shouldn't happen, but stay safe.
        while len(self.chrome._view_stack) > 1:
            self.chrome.pop_view()

    # ----- hotkey actions ---------------------------------------------------

    def _slot_for_visible(self) -> int | None:
        """Index of the registry slot whose ``service.view`` is currently visible."""
        if self.chrome is None:
            return None
        visible = self.chrome.current_visible()
        for s in self.registry.slots():
            if getattr(s.service, "view", None) is visible:
                return s.index
        return None

    def action_slot_jump(self, index: int) -> None:
        """Alt+N: focus the SERVICE in slot N (no-op if empty)."""
        if self.chrome is None:
            return
        svc = self.registry.by_index(index)
        if svc is None:
            return
        view = getattr(svc, "view", None)
        if view is None:
            return
        self.chrome.show_existing(view)
        try:
            view.focus()
        except Exception:
            pass
        self._refresh_chrome()

    def action_menu_jump(self) -> None:
        self.return_to_menu()
        self._refresh_chrome()

    def action_cycle_next(self) -> None:
        self._cycle(+1)

    def action_cycle_prev(self) -> None:
        self._cycle(-1)

    def _cycle(self, direction: int) -> None:
        if self.chrome is None:
            return
        slots = self.registry.slots()
        if not slots:
            return
        indices = [s.index for s in slots]
        visible = self.chrome.current_visible()
        try:
            cur = next(
                s.index for s in slots
                if getattr(s.service, "view", None) is visible
            )
            pos = indices.index(cur)
        except StopIteration:
            pos = -direction
        nxt = indices[(pos + direction) % len(indices)]
        self.action_slot_jump(nxt)

    async def action_close_service(self) -> None:
        """Ctrl+W: purge + unmount the current service, or leave ACTION."""
        if self.chrome is None:
            return
        visible = self.chrome.current_visible()
        if visible is None:
            return
        flavour = getattr(visible, "flavour", None)
        if flavour == "ACTION":
            # Ctrl+W on an ACTION view == Esc: tear it down, go to menu.
            self.leave_tool(visible)
            return
        slot_idx = self._slot_for_visible()
        if slot_idx is None:
            return
        await self.registry.close(slot_idx)
        self.return_to_menu()
        if visible in self.chrome._view_stack:
            self.chrome._view_stack.remove(visible)
            try:
                visible.remove()
            except Exception:
                pass
        self._refresh_chrome()

    async def action_purge_quit(self) -> None:
        n = len(self.registry)
        if n and self.chrome is not None:
            self.chrome.flash(f"purging {n} service(s)...", seconds=4.0)
        try:
            await asyncio.wait_for(self.registry.close_all(), timeout=4.0)
        except asyncio.TimeoutError:
            pass
        self.exit()

    # ----- new-instance + overlays + slot-switcher routing -----------------

    def action_new_tool(self, digit: int) -> None:
        """Shift+digit / symbol-row: spawn a NEW instance.

        For SERVICE-flavour tools this opens a second VOID / second
        MIRAGE / etc. in the next free slot.  For ACTION-flavour
        tools it is identical to plain ``<digit>`` (you cannot have
        two foreground actions anyway).
        """
        name = self._tool_for_digit(digit)
        if name is None:
            return
        self.enter_tool(name, new_instance=True)

    @staticmethod
    def _tool_for_digit(d: int) -> str | None:
        return {
            1: "void", 2: "mask", 3: "strip", 4: "carrier", 5: "mirage",
        }.get(d)

    def action_help_overlay(self) -> None:
        """F1 / Alt+H: open the help overlay over the current view."""
        if self.chrome is None:
            return
        from shared.ui.overlay import (
            HelpOverlay, KeyBinding, bindings_from_class, tagline_from_docstring,
        )
        visible = self.chrome.current_visible()
        view_name = type(visible).__name__ if visible is not None else ""
        view_tagline = (
            tagline_from_docstring(type(visible)) if visible is not None else ""
        )
        view_bindings = (
            bindings_from_class(type(visible)) if visible is not None else []
        )
        suite_bindings = self._suite_help_bindings()
        self.push_screen(HelpOverlay(
            suite_bindings=suite_bindings,
            view_bindings=view_bindings,
            view_name=view_name,
            view_tagline=view_tagline,
        ))

    @staticmethod
    def _suite_help_bindings() -> list:
        """Canonical suite-level binding list shown in the help overlay.

        Mirrors docs/NAVIGATION.md section 2.1 verbatim.
        """
        from shared.ui.overlay import KeyBinding
        return [
            KeyBinding("F1 / Alt+H",    "open this help"),
            KeyBinding("Alt+M",          "slot switcher"),
            KeyBinding("Alt+0",          "return to menu"),
            KeyBinding("Alt+1..Alt+9",   "jump to SERVICE in slot N"),
            KeyBinding("Alt+] / Alt+[",  "cycle next / prev SERVICE"),
            KeyBinding("Shift+1..5",     "new instance of tool N"),
            KeyBinding("Ctrl+W",         "close current SERVICE"),
            KeyBinding("Ctrl+C / Ctrl+Q","quit suite (purges all)"),
        ]

    def action_slot_switcher(self) -> None:
        """Alt+M: open the slot switcher overlay."""
        if self.chrome is None:
            return
        from shared.ui.overlay import SlotSwitcherOverlay, SlotRow
        rows: list[SlotRow] = []
        for s in self.registry.slots():
            try:
                line = s.service.status_line()
            except Exception:
                line = "?"
            rows.append(SlotRow(
                index=s.index,
                name=getattr(s.service, "name", "?"),
                status=line,
            ))
        # Plus the foreground ACTION view, if any (one extra row).
        action_view = self._current_action_view()
        if action_view is not None:
            rows.append(SlotRow(
                index=0,
                name=getattr(action_view, "name", type(action_view).__name__),
                status="foreground action",
                is_action=True,
            ))
        self.push_screen(SlotSwitcherOverlay(rows))

    def _current_action_view(self) -> Widget | None:
        if self.chrome is None:
            return None
        for v in self.chrome._view_stack:
            if getattr(v, "flavour", None) == "ACTION":
                return v
        return None

    def slot_switcher_jump(self, row) -> None:
        """Overlay -> chrome callback: jump to the selected slot/action."""
        if row is None or self.chrome is None:
            return
        if row.is_action:
            v = self._current_action_view()
            if v is not None:
                self.chrome.show_existing(v)
                try:
                    v.focus()
                except Exception:
                    pass
                self._refresh_chrome()
            return
        self.action_slot_jump(row.index)

    def slot_switcher_close(self, row) -> None:
        """Overlay -> chrome callback: close the selected slot/action."""
        if row is None or self.chrome is None:
            return
        if row.is_action:
            v = self._current_action_view()
            if v is not None:
                self.leave_tool(v)
            return
        async def _do() -> None:
            await self.registry.close(row.index)
            # If the closed slot's view was visible, return to menu.
            self.return_to_menu()
            self._refresh_chrome()
        # Schedule on the running loop -- this callback can fire
        # either from the overlay's action handler (running on the
        # Textual loop) or, in tests, synchronously.
        try:
            asyncio.get_event_loop().create_task(_do())
        except RuntimeError:
            # No loop -- best effort: just clear the registry entry.
            try:
                self.registry._slots.pop(row.index, None)
            except Exception:
                pass

    # ----- VOID's hand-off bridge (Phase 7 v1.0 bridge) --------------------

    def void_session_bridge(self, args: dict) -> None:
        """VoidView calls this when the user submits the lobby form.

        Phase 7 v1.0 (see RELEASE_NOTES "Known deviations"):  the
        chat / connecting / starmap flows still live as Textual
        Screen subclasses under ``tools/void/client/app.py``.  Until
        those are reborn as in-chrome views, we hand back to
        ``babel.__main__`` to relaunch the legacy ``VoidApp`` with
        the populated arguments.

        Stashed on a class attribute the harness picks up post-exit;
        the test harness can read it without a real Textual loop.
        """
        self._void_session_args = dict(args)
        self.exit()

