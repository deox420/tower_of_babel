"""In-chrome tool home views.

When the user picks a tool from the main menu, the chrome mounts the
corresponding view in its content slot. v2.0.0 status:

* **MASK, STRIP, CARRIER, MIRAGE**: fully interactive in-chrome views.
  Their real widget trees live in ``tools/<tool>/app.py`` and inherit
  from :class:`ToolHomeView`. The chrome owns the outer frame and the
  footer; the tool view owns the content slot.
* **VOID**: transitional. The home view is the v1.0 info card with one
  added binding — `[Enter]` exits the chrome with ``return_value=
  ("launch_void", argv)`` so ``babel.__main__`` can re-exec VOID as
  its standalone app. Full migration of VOID's lobby/connecting/chat
  screens into the chrome is tracked for v2.1.0
  (docs/V2_REDESIGN.md §7.5; the screens currently inherit from
  ``textual.Screen`` and would each need to become a Container).

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
    name = "VOID"
    flavour = "SERVICE"
    logo = art.VOID_LOGO
    summary = (
        "Ephemeral encrypted messenger over Tor. X3DH initial AKE + "
        "Double Ratchet per-message keys. Fresh identity per session, "
        "no key material on disk, /burn wipes RAM on exit."
    )
    cli_examples = [
        ("babel --exec void",                "open the lobby"),
        ("babel --exec void --make-invite",  "host a room, print a void:// link"),
        ("babel --exec void --setup",        "diagnostic (tor / mlock / xeddsa)"),
    ]
    threat_note = (
        "VOID's full in-chrome migration is deferred to v2.1.0; pressing "
        "[Enter] here briefly suspends the suite and runs VOID standalone. "
        "When VOID exits you return to the babel menu."
    )

    BINDINGS = [
        Binding("escape", "leave",  "back to menu", show=True, priority=True),
        Binding("alt+0",  "leave",  "menu",          show=False, priority=True),
        Binding("enter",  "launch", "launch VOID",   show=True),
    ]

    def status_line(self) -> str:
        return "ready"

    def action_launch(self) -> None:
        """Exit the suite app with a return-value hand-off.

        ``babel.__main__._run_menu`` inspects ``app.return_value`` and,
        if it's ``("launch_void", argv)``, runs VOID standalone with
        those argv. When VOID exits the menu is re-launched, restoring
        the v1.0 flow until VOID's screens are fully ported.
        """
        app = self.app
        try:
            app.exit(result=("launch_void", []))
        except TypeError:
            try:
                app.exit(("launch_void", []))
            except Exception:
                app.exit()


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
    if name == "void":
        return VoidHomeView
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
    return ["void", "mask", "strip", "carrier", "mirage"]


__all__ = [
    "ToolHomeView",
    "VoidHomeView",
    "view_class_for",
    "all_tool_names",
]
