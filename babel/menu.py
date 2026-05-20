"""Tower of Babel main menu — v2.0.0.

Renders the five-entry menu from MASTER.md Section 6.1 as a *view*
that mounts inside ``babel.shell.Chrome``'s content slot. The chrome
owns the outer frame and the footer; the menu owns its card-shaped
centerpiece.

All five entries are live: MASK, STRIP, CARRIER and MIRAGE mount their
real interactive views in-chrome (``tools/<tool>/app.py``); VOID
mounts a transitional info card whose ``[Enter]`` binding exits the
suite app so ``babel.__main__`` can launch ``VoidApp`` standalone.
When VOID exits the suite app re-launches and the user lands back on
this menu. See docs/V2_REDESIGN.md §7.5 for the v2.1.0 plan to bring
VOID fully in-chrome.
"""
from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Static

from babel import theme
from babel.art import (
    BABEL_HINTS,
    BABEL_LOGO,
    BABEL_LOGO_NARROW,
    BABEL_TAGLINE,
    SCANLINE,
)


# Order matches MASTER.md Section 7 table.  Live=True means the entry
# launches a real tool; False renders dimmed and the keypress no-ops.
TOOLS = [
    ("1", "VOID",    "ephemeral encrypted messenger",        True),
    ("2", "MASK",    "disposable identity generator",        True),
    ("3", "STRIP",   "metadata laundry",                     True),
    ("4", "CARRIER", "steganography",                        True),
    ("5", "MIRAGE",  "cover traffic generator",              True),
]


class MainMenuView(Container):
    """Phase 1 menu, mounted in the chrome's content slot.

    Lives as a Container (not a Screen) so the chrome frame keeps
    rendering above and below it.  Bindings are scoped to the
    container; the chrome registers global Alt+digit / Ctrl+W /
    Ctrl+C handlers above us.

    ``can_focus = True`` is required: a Container is not focusable by
    default, and Textual only dispatches a widget's BINDINGS when
    that widget (or one of its ancestors) sits in the focus chain.
    Without this the menu rendered correctly but pressing 1..5 / q
    did nothing.  We also call ``focus()`` in ``on_mount`` so the
    user can start typing immediately.
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
        /* Width pinned to the wide BABEL_LOGO width + padding so the
           container has a real size for the parent's align rules to
           hang on.  `width: auto` regressed under Textual 8.x: the
           Vertical computed to 0x0 and nothing inside it rendered
           (Phase 6 hotfix: user reported "borders + black screen"). */
        height: auto;
        width: 60;
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
    MainMenuView .hint {{
        width: 100%;
        color: {theme.CYAN};
        text-style: dim italic;
    }}
    """

    BINDINGS = [
        Binding("1", "select('void')",    "void",    show=False),
        Binding("2", "select('mask')",    "mask",    show=False),
        Binding("3", "select('strip')",   "strip",   show=False),
        Binding("4", "select('carrier')", "carrier", show=False),
        Binding("5", "select('mirage')",  "mirage",  show=False),
        Binding("q", "app.purge_quit",    "quit",    show=False, priority=True),
        # `h` (3-panel first-time wizard, MASTER.md 6.2) and `s` (TUI
        # setup aggregator, 6.3) are deferred post-1.0.  CLI paths
        # (`babel --help`, `babel --setup`) cover both today; the TUI
        # bindings are intentionally absent so the menu hint never
        # advertises a stub.  See RELEASE_NOTES.md "Known deviations".
    ]

    def on_mount(self) -> None:
        """Grab keyboard focus so 1-5 / q bindings fire immediately."""
        try:
            self.focus()
        except Exception:
            # Pre-render focus calls can race in some Textual versions;
            # the menu will still take focus on the next user keypress.
            pass

    def compose(self) -> ComposeResult:
        logo = BABEL_LOGO if not theme.is_compact() else BABEL_LOGO_NARROW
        with Vertical(id="menu-card"):
            yield Static(logo, classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(SCANLINE, classes="scanline")
            yield Static(" ")
            for key, name, tag, live in TOOLS:
                cls = "menu-row" if live else "menu-row dim"
                suffix = "" if live else "  (not yet built)"
                yield Static(f"  [{key}]  {name:<8}  {tag}{suffix}",
                             classes=cls)
            yield Static(" ")
            yield Static(
                f"// {random.choice(BABEL_HINTS)}      [q] quit",
                classes="hint",
            )

    # ----- actions ---------------------------------------------------------

    def action_select(self, tool: str) -> None:
        """Hand the chrome a chosen tool name.

        ``ChromeApp.enter_tool`` mounts the tool's home view in the
        content slot. For MASK/STRIP/CARRIER/MIRAGE this is the real
        interactive view from ``tools/<tool>/app.py``; for VOID it's
        the transitional info card whose ``[Enter]`` triggers a
        re-exec into the standalone client (see ``babel.__main__``).
        """
        self.app.enter_tool(tool)

    def action_noop(self, _tool: str) -> None:
        """Stubs for features not yet built (entries 2-5, [h], [s])."""
        return
