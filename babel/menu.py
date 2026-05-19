"""Tower of Babel main menu.

Phase 7 (MASTER.md 6.1, docs/NAVIGATION.md sections 2.2 + 6 + 9):

The menu mounts inside ``babel.shell.Chrome``'s content slot.  The
chrome owns the frame and the footer; the menu owns the card.

Behaviour:

* Digits 1..5 enter the corresponding tool (chrome.enter_tool).
* Shift+1..5 (and the !@#$% symbol-row fallbacks for F-Droid Termux)
  force a new instance via chrome.enter_tool(..., new_instance=True).
* ``q`` quits the suite (same purge path as Ctrl+C).
* Each menu row reflects the live registry state: a SERVICE entry
  whose slot is occupied renders with ``(live in slot N)`` so the
  user knows what Alt+N will land on.
* The paste field at the bottom routes ``void://`` / ``mask://``
  / ``carrier://`` URLs to the right tool with ``prefill`` set
  (shared.link.invite.looks_like is the gateway).
* On the Termux 60-col floor the inline paste field is replaced by
  a hint "press <p> to paste a link" and a sub-screen that opens
  with the same field.
"""
from __future__ import annotations

import random
from typing import Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Input, Static

from babel import theme
from babel.art import (
    BABEL_HINTS,
    BABEL_LOGO,
    BABEL_LOGO_NARROW,
    BABEL_TAGLINE,
    SCANLINE,
)
from babel.views import tool_meta_all


# Order matches MASTER.md Section 7 table.  Live=True means the entry
# launches a real tool; False renders dimmed and the keypress no-ops.
TOOLS = [
    ("1", "void",    "VOID",    "ephemeral encrypted messenger", True),
    ("2", "mask",    "MASK",    "disposable identity generator", True),
    ("3", "strip",   "STRIP",   "metadata laundry",              True),
    ("4", "carrier", "CARRIER", "steganography",                 True),
    ("5", "mirage",  "MIRAGE",  "cover traffic generator",       True),
]


PASTE_PLACEHOLDER = (
    "// paste a void:// / mask:// / carrier:// link to autofill ..."
)


class _PasteSubScreen(Container):
    """60-col fallback: just the paste Input, fills the content slot.

    Mounted by MainMenuView.action_open_paste when the chrome is at
    the Termux floor and there is no room for an inline field.  Esc
    or Enter (after a successful route) tears it down.
    """

    can_focus = True

    DEFAULT_CSS = f"""
    _PasteSubScreen {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    _PasteSubScreen .hint  {{ color: {theme.CYAN}; text-style: dim italic; }}
    _PasteSubScreen .err   {{ color: {theme.RED}; }}
    _PasteSubScreen Input  {{
        background: {theme.BG}; color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    """

    BINDINGS = [
        Binding("escape", "leave", "back", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._err: Static | None = None

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("PASTE A LINK", classes="hint")
            yield Input(placeholder=PASTE_PLACEHOLDER, id="paste-link")
            self._err = Static("", classes="hint")
            yield self._err
            yield Static("[Esc] back to menu", classes="hint")

    def on_mount(self) -> None:
        try:
            self.query_one("#paste-link", Input).focus()
        except Exception:
            pass

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = (event.value or "").strip()
        if not text:
            return
        outcome = route_paste(self.app, text)
        if outcome:
            return
        if self._err is not None:
            self._err.update(
                "unknown scheme; expected void:// / mask:// / carrier://"
            )
            self._err.set_classes("err")

    def action_leave(self) -> None:
        leave = getattr(self.app, "leave_tool", None)
        if callable(leave):
            leave(self)


def route_paste(app, text: str) -> bool:
    """Route a pasted link to the right tool.  Returns True on success.

    Pure routing function so the pentest harness can exercise it
    without instantiating a real Textual app.
    """
    from shared.link.invite import looks_like, SCHEME_VOID, SCHEME_MASK, SCHEME_CARRIER
    scheme = looks_like(text)
    if scheme is None:
        return False
    tool_for_scheme = {
        SCHEME_VOID:    "void",
        SCHEME_MASK:    "mask",
        SCHEME_CARRIER: "carrier",
    }
    tool = tool_for_scheme.get(scheme)
    if tool is None:
        return False
    enter = getattr(app, "enter_tool", None)
    if callable(enter):
        enter(tool, prefill={"link": text})
    return True


class MainMenuView(Container):
    """Phase 7 menu, mounted in the chrome's content slot.

    Tool entries reflect live slot state.  The paste field at the
    bottom routes void:// / mask:// / carrier:// URLs to the right
    tool.  The field is not auto-focused so digit keys keep working
    without clicking the field.
    """

    can_focus = True

    DEFAULT_CSS = f"""
    MainMenuView {{
        align: center middle;
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
    }}
    MainMenuView #menu-card {{
        height: auto;
        width: 64;
        padding: 1 2;
        background: {theme.BG};
    }}
    MainMenuView .title {{
        width: 100%;
        color: {theme.GREEN};
        text-style: bold;
        text-align: center;
    }}
    MainMenuView .tagline {{
        width: 100%;
        color: {theme.CYAN};
        text-style: dim italic;
        text-align: center;
    }}
    MainMenuView .scanline {{
        width: 100%;
        color: {theme.GREEN_DEEP};
        text-style: dim;
        text-align: center;
    }}
    MainMenuView .menu-row {{
        width: 100%;
        color: {theme.GREEN};
    }}
    MainMenuView .menu-row.dim {{
        width: 100%;
        color: {theme.MUTE};
        text-style: dim;
    }}
    MainMenuView .menu-row.live {{
        width: 100%;
        color: {theme.CYAN};
    }}
    MainMenuView .hint {{
        width: 100%;
        color: {theme.CYAN};
        text-style: dim italic;
    }}
    MainMenuView .err {{
        width: 100%;
        color: {theme.RED};
    }}
    MainMenuView Input {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    """

    BINDINGS = [
        Binding("1", "select('void')",    "void",    show=False),
        Binding("2", "select('mask')",    "mask",    show=False),
        Binding("3", "select('strip')",   "strip",   show=False),
        Binding("4", "select('carrier')", "carrier", show=False),
        Binding("5", "select('mirage')",  "mirage",  show=False),
        Binding("p", "open_paste",        "paste",   show=False),
        Binding("q", "app.purge_quit",    "quit",    show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._row_widgets: dict[str, Static] = {}
        self._paste_err: Static | None = None

    def on_mount(self) -> None:
        try:
            self.focus()
        except Exception:
            pass
        # Re-render menu rows every second so "(live in slot N)"
        # tracks registry changes without an explicit signal.
        self.set_interval(1.0, self._refresh_rows)

    def compose(self) -> ComposeResult:
        narrow = theme.is_very_compact()
        logo = BABEL_LOGO_NARROW if theme.is_compact() else BABEL_LOGO
        with Vertical(id="menu-card"):
            yield Static(logo, classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(SCANLINE, classes="scanline")
            yield Static(" ")
            for key, slug, name, tag, live in TOOLS:
                row = Static(self._row_text(key, name, tag, live, slug),
                             classes=self._row_class(slug, live))
                self._row_widgets[slug] = row
                yield row
            yield Static(" ")
            if not narrow:
                yield Static(
                    "// paste a void:// / mask:// / carrier:// link below "
                    "(or press digits 1-5)",
                    classes="hint",
                )
                yield Input(placeholder=PASTE_PLACEHOLDER, id="paste-link")
                self._paste_err = Static("", classes="hint")
                yield self._paste_err
            else:
                yield Static(
                    "// press [p] to paste a void:// / mask:// link",
                    classes="hint",
                )
            yield Static(
                f"// {random.choice(BABEL_HINTS)}      [q] quit   [F1] help",
                classes="hint",
            )

    # ----- row rendering ----------------------------------------------------

    def _registry(self):
        return getattr(self.app, "registry", None)

    def _live_slot_for(self, slug: str) -> int | None:
        reg = self._registry()
        if reg is None:
            return None
        meta = tool_meta_all().get(slug, {})
        name = meta.get("name")
        if not name:
            return None
        existing = reg.by_name(name)
        if existing is None:
            return None
        return existing[0]

    def _row_text(self, key: str, name: str, tag: str, live: bool,
                  slug: str) -> str:
        if not live:
            return f"  [{key}]  {name:<8}  {tag}  (not yet built)"
        slot = self._live_slot_for(slug)
        if slot is not None:
            # Tighter format -- the user already knows the tag.
            return f"  [{key}]  {name:<8}  (live in slot {slot})"
        return f"  [{key}]  {name:<8}  {tag}"

    def _row_class(self, slug: str, live: bool) -> str:
        if not live:
            return "menu-row dim"
        if self._live_slot_for(slug) is not None:
            return "menu-row live"
        return "menu-row"

    def _refresh_rows(self) -> None:
        for key, slug, name, tag, live in TOOLS:
            row = self._row_widgets.get(slug)
            if row is None:
                continue
            row.update(self._row_text(key, name, tag, live, slug))
            row.set_classes(self._row_class(slug, live))

    # ----- actions ----------------------------------------------------------

    def action_select(self, tool: str) -> None:
        self.app.enter_tool(tool)

    def action_open_paste(self) -> None:
        """60-col fallback: open the paste sub-screen."""
        push = getattr(self.app, "push_view", None)
        if callable(push):
            push(_PasteSubScreen())

    # ----- paste-field handlers --------------------------------------------

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "paste-link":
            return
        text = (event.value or "").strip()
        if not text:
            return
        # Clear the field whether routing worked or not so a typo
        # doesn't sit around looking authoritative.
        event.input.value = ""
        ok = route_paste(self.app, text)
        if self._paste_err is not None:
            if ok:
                self._paste_err.update("")
                self._paste_err.set_classes("hint")
            else:
                self._paste_err.update(
                    "unknown scheme; expected void:// / mask:// / carrier://"
                )
                self._paste_err.set_classes("err")


__all__ = ["MainMenuView", "route_paste"]
