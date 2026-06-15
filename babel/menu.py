"""Tower of Babel main menu — v2.0.0.

Renders the five-entry menu from MASTER.md Section 6.1 as a *view*
that mounts inside ``babel.shell.Chrome``'s content slot. The chrome
owns the outer frame and the footer; the menu owns its card-shaped
centerpiece.

All entries are live in-chrome. MASK, STRIP, CARRIER, MIRAGE and the
VOID **client** (VOID-C) mount real interactive views in the content
slot (``tools/<tool>/app.py`` and ``tools/void/client/chrome_view.py``).
The VOID **server** modes (VOID-S, VOID-SC) are relay/onion-hosting
daemons rather than chat UIs, so their info cards still ``[Enter]``-exit
the suite to run ``void-server`` / ``void --make-invite`` standalone and
return to this menu on exit.
"""
from __future__ import annotations

import random

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Button, Static

from babel import theme
from babel.art import (
    BABEL_HINTS,
    BABEL_LOGO,
    BABEL_LOGO_NARROW,
    BABEL_TAGLINE,
    SCANLINE,
)


# Seven entries in v2.0.x polish #2: VOID is split into three modes
# (server-only / server+client / client-only) so the user picks the
# operating mode at launch. The (hotkey, slug, display name, tag) tuple
# drives both the keybinding and the Button row.
TOOLS = [
    ("1", "void-s",  "VOID-S",  "encrypted messenger — server only"),
    ("2", "void-sc", "VOID-SC", "encrypted messenger — server + client"),
    ("3", "void-c",  "VOID-C",  "encrypted messenger — client only"),
    ("4", "mask",    "MASK",    "disposable identity generator"),
    ("5", "strip",   "STRIP",   "metadata laundry"),
    ("6", "carrier", "CARRIER", "steganography"),
    ("7", "mirage",  "MIRAGE",  "cover traffic generator"),
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
    # Mirror Chrome's setting — see babel.shell.Chrome for the click
    # crash this guards against on Textual 4.x / Python 3.14.
    ALLOW_SELECT = False

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
        /* Each row is a Button styled to look like the v1 Static row.
           Borderless until hover/focus so the menu stays clean. */
        width: 100%;
        height: 3;
        background: {theme.BG};
        color: {theme.GREEN};
        border: none;
        padding: 0 0;
        margin: 0 0;
        text-align: left;
    }}
    MainMenuView .menu-row:hover {{
        background: {theme.GREEN_DEEP};
        color: {theme.CYAN};
        border: none;
    }}
    MainMenuView .menu-row:focus {{
        color: {theme.CYAN};
        text-style: bold;
        border: none;
    }}
    MainMenuView .hint {{
        width: 100%;
        color: {theme.CYAN};
        text-style: dim italic;
        text-align: center;
        margin-top: 1;
    }}
    """

    BINDINGS = [
        Binding("1", "select('void-s')",  "void-s",  show=False),
        Binding("2", "select('void-sc')", "void-sc", show=False),
        Binding("3", "select('void-c')",  "void-c",  show=False),
        Binding("4", "select('mask')",    "mask",    show=False),
        Binding("5", "select('strip')",   "strip",   show=False),
        Binding("6", "select('carrier')", "carrier", show=False),
        Binding("7", "select('mirage')",  "mirage",  show=False),
        Binding("q", "app.purge_quit",    "quit",    show=False, priority=True),
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
            for key, slug, name, tag in TOOLS:
                yield Button(
                    f"  [{key}]  {name:<8}  {tag}",
                    id=f"menu-{slug}",
                    classes="menu-row",
                )
            yield Static(" ")
            yield Static(
                f"// {random.choice(BABEL_HINTS)}      [1-7] tool   [q] quit",
                classes="hint",
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Click on a menu row → same path as pressing the digit."""
        button_id = event.button.id or ""
        if button_id.startswith("menu-"):
            self.action_select(button_id[len("menu-"):])

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
