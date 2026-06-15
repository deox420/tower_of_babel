"""In-chrome tool home views.

When the user picks a tool from the main menu, the chrome mounts the
corresponding view in its content slot. v2.0.0 status:

* **MASK, STRIP, CARRIER, MIRAGE**: fully interactive in-chrome views.
  Their real widget trees live in ``tools/<tool>/app.py`` and inherit
  from :class:`ToolHomeView`. The chrome owns the outer frame and the
  footer; the tool view owns the content slot.
* **VOID client (VOID-C)**: fully interactive in-chrome. The lobby,
  connecting, and chat stages live in
  ``tools/void/client/chrome_view.VoidView`` (a SERVICE-flavour
  ``ToolHomeView``) and are driven by the shared
  ``tools.void.client.session.VoidSession`` controller — the same
  controller the standalone ``VoidApp`` uses.
* **VOID server (VOID-S, VOID-SC)**: still transitional. These run a
  relay daemon / host an ephemeral .onion rather than presenting a chat
  UI, so their home views keep the info-card hand-off: `[Enter]` exits
  the chrome with ``return_value=("launch_void", argv)`` and
  ``babel.__main__`` re-execs the server/host standalone.

Each subclass declares:

* ``name``     -- short uppercase tool name (matches the menu).
* ``flavour``  -- ``"SERVICE"`` keeps the view in a slot when the user
  returns to the menu; ``"ACTION"`` is torn down on return.
* ``logo``    -- pre-rendered ASCII banner from ``babel.art``.
* ``summary`` -- one-paragraph blurb (for the info-card fallback).
* ``cli_examples`` -- list of ``(command, gloss)`` tuples.

The base class also implements the chrome's ``Service`` Protocol so
service-flavoured tools can register with the registry without any
extra boilerplate.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from babel import art, theme


_FLAVOUR_LITERAL = Literal["SERVICE", "ACTION"]


class ToolHomeView(Vertical):
    """Home view for one tool, mounted inside the chrome's content slot.

    Subclasses set the class-level attrs. The view is focusable so its
    bindings fire as soon as it's pushed.

    ``ALLOW_SELECT = False``: mirrors the setting on ``Chrome`` so
    Textual 4.x's text-selection logic stays off across the whole
    suite (see ``babel.shell.Chrome`` for the crash this avoids).
    """

    name: ClassVar[str] = "?"
    flavour: ClassVar[_FLAVOUR_LITERAL] = "ACTION"
    logo: ClassVar[str] = ""
    summary: ClassVar[str] = ""
    cli_examples: ClassVar[list[tuple[str, str]]] = []
    threat_note: ClassVar[str] = ""

    can_focus = True
    ALLOW_SELECT = False

    BINDINGS = [
        Binding("escape", "leave", "back to menu", show=True, priority=True),
        Binding("alt+0",  "leave", "menu",          show=False, priority=True),
    ]

    DEFAULT_CSS = f"""
    ToolHomeView {{
        align: center top;
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    ToolHomeView #tool-card {{
        height: auto;
        width: 90%;
        max-width: 100;
        padding: 1 2;
        background: {theme.BG};
    }}
    ToolHomeView .logo {{
        width: 100%;
        color: {theme.GREEN};
        text-style: bold;
        text-align: center;
        height: auto;
    }}
    ToolHomeView .flavour-tag {{
        width: 100%;
        color: {theme.AMBER};
        text-style: dim italic;
        text-align: center;
    }}
    ToolHomeView .summary {{
        width: 100%;
        color: {theme.GREEN};
        margin-top: 1;
        margin-bottom: 1;
    }}
    ToolHomeView .section {{
        width: 100%;
        color: {theme.CYAN};
        text-style: bold;
        margin-top: 1;
    }}
    ToolHomeView .cli-row {{
        width: 100%;
        color: {theme.GREEN};
    }}
    ToolHomeView .cli-gloss {{
        width: 100%;
        color: {theme.MUTE};
        text-style: dim;
    }}
    ToolHomeView .threat {{
        width: 100%;
        color: {theme.AMBER};
        text-style: italic;
        margin-top: 1;
    }}
    ToolHomeView .keys {{
        width: 100%;
        color: {theme.CYAN};
        text-style: dim;
        text-align: center;
        margin-top: 1;
    }}
    """

    def on_mount(self) -> None:
        try:
            self.focus()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        compact = theme.is_compact()
        with Vertical(id="tool-card"):
            yield Static(self.logo, classes="logo")
            flavour_word = "service" if self.flavour == "SERVICE" else "action"
            yield Static(f"-- {self.name} ({flavour_word}) --",
                         classes="flavour-tag")
            yield Static(self.summary, classes="summary")
            if self.cli_examples:
                yield Static("Quick start (CLI):", classes="section")
                for cmd, gloss in self.cli_examples:
                    if compact:
                        yield Static(f"  {cmd}", classes="cli-row")
                        yield Static(f"    {gloss}", classes="cli-gloss")
                    else:
                        yield Static(f"  {cmd}", classes="cli-row")
                        yield Static(f"      {gloss}", classes="cli-gloss")
            if self.threat_note:
                yield Static("Honest threat note:", classes="section")
                yield Static(self.threat_note, classes="threat")
            if self.flavour == "SERVICE":
                hint = "[Alt+0] background to slot   [Esc] return to menu"
            else:
                hint = "[Esc] return to menu"
            yield Static(hint, classes="keys")

    # ----- chrome action handlers ---------------------------------------

    def action_leave(self) -> None:
        """Esc / Alt+0 -- hand control back to the chrome.

        The chrome decides what 'leave' means based on flavour:
        * SERVICE: hide the view but keep this instance registered in
          the slot so Alt+N can bring it back.
        * ACTION: pop and discard.
        """
        app = self.app
        leave = getattr(app, "leave_tool", None)
        if callable(leave):
            leave(self)
        else:
            ret = getattr(app, "return_to_menu", None)
            if callable(ret):
                ret()

    # ----- Service Protocol (used when flavour == "SERVICE") -----------

    def status_line(self) -> str:
        return "idle"

    def footer_contribution(self) -> dict:
        return {}

    def resource_caps(self) -> dict:
        return {}

    async def purge_local(self) -> None:
        """Default: no in-RAM state to purge."""
        return None


# ---------------------------------------------------------------------------
# VOID — transitional info-card. Full in-chrome migration is v2.1.0 work.
# ---------------------------------------------------------------------------


class VoidHomeView(ToolHomeView):
    """Base info card for VOID. Three subclasses below pick the launch mode.

    Full in-chrome migration is still v2.1.0 work. Pressing [Enter]
    on any VOID home view exits the suite app with
    ``("launch_void", argv)``, and ``babel.__main__._run_menu``
    re-execs VoidApp with that argv. The three subclasses differ
    only in the argv they hand back, so each menu entry picks a
    mode without requiring per-mode TUI scaffolding.
    """
    name = "VOID"
    flavour = "SERVICE"
    logo = art.VOID_LOGO
    summary = (
        "Ephemeral encrypted messenger over Tor. X3DH initial AKE + "
        "Double Ratchet per-message keys. Fresh identity per session, "
        "no key material on disk, /burn wipes RAM on exit."
    )
    cli_examples = [
        ("babel --exec void",                "open the lobby (client)"),
        ("babel --exec void --host",         "run a void-server daemon"),
        ("babel --exec void --make-invite",  "host a room + print void:// link"),
        ("babel --exec void --setup",        "diagnostic (tor / mlock / xeddsa)"),
    ]
    threat_note = (
        "VOID's full in-chrome migration is deferred to v2.1.0; pressing "
        "[Enter] here briefly suspends the suite and runs VOID standalone. "
        "When VOID exits you return to the babel menu."
    )

    # Subclasses override this to inject the launch flag.
    _launch_argv: tuple[str, ...] = ()

    BINDINGS = [
        Binding("escape", "leave",  "back to menu", show=True, priority=True),
        Binding("alt+0",  "leave",  "menu",          show=False, priority=True),
        Binding("enter",  "launch", "launch VOID",   show=True),
    ]

    def status_line(self) -> str:
        return "ready"

    def action_launch(self) -> None:
        app = self.app
        argv = list(self._launch_argv)
        try:
            app.exit(result=("launch_void", argv))
        except TypeError:
            try:
                app.exit(("launch_void", argv))
            except Exception:
                app.exit()


class VoidServerOnlyView(VoidHomeView):
    """VOID-S: run only the relay daemon (no chat UI)."""
    name = "VOID-S"
    summary = (
        "VOID server-only mode. Runs the relay daemon that other VOID "
        "clients connect to. Pure server — no chat UI on this side. "
        "Useful when this host is the meeting point."
    )
    threat_note = (
        "Press [Enter] to suspend the suite and start a void-server "
        "process in this terminal. Ctrl+C stops the server and returns "
        "you to the babel menu."
    )
    _launch_argv = ("--host",)


class VoidServerClientView(VoidHomeView):
    """VOID-SC: spawn an ephemeral server + a client invite link."""
    name = "VOID-SC"
    summary = (
        "VOID server + client. Spawns an ephemeral .onion relay on "
        "this host, runs the server, and prints a void:// invite link "
        "your peer can paste into their own VOID client."
    )
    threat_note = (
        "Press [Enter] to suspend the suite and run `void --make-invite`. "
        "The server lives only while this command is open; when you exit "
        "you return to the babel menu and the .onion is torn down."
    )
    _launch_argv = ("--make-invite",)


class VoidClientOnlyView(VoidHomeView):
    """VOID-C: open the standard VOID lobby as a client."""
    name = "VOID-C"
    summary = (
        "VOID client-only mode. Opens the VOID lobby; you point it at "
        "a remote .onion or ws:// server URL and join a room. No server "
        "is hosted on this side."
    )
    threat_note = (
        "Press [Enter] to suspend the suite and open the VOID client. "
        "When the client exits you return to the babel menu."
    )
    _launch_argv = ()


# ---------------------------------------------------------------------------
# Registry / lookup
# ---------------------------------------------------------------------------
#
# MASK / STRIP / CARRIER / MIRAGE live in their tool packages as
# `<Tool>View(ToolHomeView)` and are imported lazily so users can run
# `python -m babel --help` without dragging in Pillow, argon2-cffi,
# httpx, etc. for every cold import.


def view_class_for(tool: str) -> type[ToolHomeView] | None:
    name = tool.lower()
    # VOID has three menu entries. The CLIENT (void-c / void) is now a full
    # in-chrome interactive view (lobby -> connecting -> chat) backed by the
    # shared VoidSession controller. The SERVER modes (void-s, void-sc) are
    # relay/onion-hosting daemons rather than chat UIs, so they keep the
    # info-card hand-off that suspends the suite and runs void-server /
    # `void --make-invite` standalone.
    if name in ("void", "void-c"):
        from tools.void.client.chrome_view import VoidView
        return VoidView
    if name == "void-s":
        return VoidServerOnlyView
    if name == "void-sc":
        return VoidServerClientView
    if name == "mask":
        from tools.mask.app import MaskView
        return MaskView
    if name == "strip":
        from tools.strip.app import StripView
        return StripView
    if name == "carrier":
        from tools.carrier.app import CarrierView
        return CarrierView
    if name == "mirage":
        from tools.mirage.app import MirageView
        return MirageView
    return None


def all_tool_names() -> list[str]:
    return ["void-s", "void-sc", "void-c", "mask", "strip", "carrier", "mirage"]


__all__ = [
    "ToolHomeView",
    "VoidHomeView",
    "view_class_for",
    "all_tool_names",
]
