"""STRIP Textual screen -- mounted in the babel chrome's content slot.

Minimal interactive surface: input field for a path, the same
``render_diff`` table used by the CLI, an aggressive-mode toggle,
and a write/dry-run toggle. Full file-picker UI is Phase 2b work.

Because Phase 1's ``ChromeApp.enter_tool`` still exits the app
with ``return_value=<tool>`` (see ``babel.__main__``), STRIP runs
as its own ``StripApp`` for now. The screen is built so it can be
re-mounted under a future in-chrome view by lifting ``StripView``
out of the ``StripApp`` shell.
"""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Footer, Input, Static

from babel import theme
from babel.art import BABEL_TAGLINE
from shared.ui.diff_view import DiffTable
from tools.strip.core.pdf import EncryptedPDFError
from tools.strip.pipeline import SUPPORTED_EXTENSIONS, strip_path


class StripView(Container):
    """Metadata laundry -- EXIF / XMP / IPTC / Office props / ID3 / PDF.

    Mounted inside the babel chrome's content slot.  Action-flavoured:
    Esc tears the view down and returns to the menu.  Has no Service
    in the chrome's slot registry.
    """

    name = "STRIP"
    flavour = "ACTION"
    can_focus = True
    service = None

    DEFAULT_CSS = f"""
    StripView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
    }}
    StripView .title {{
        color: {theme.GREEN};
        text-style: bold;
    }}
    StripView .tagline {{
        color: {theme.CYAN};
        text-style: dim italic;
    }}
    StripView .status {{
        color: {theme.MUTE};
    }}
    StripView .status.warn {{
        color: {theme.AMBER};
    }}
    StripView .status.err {{
        color: {theme.RED};
    }}
    StripView Input {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    StripView #diff {{
        height: 1fr;
        overflow-y: auto;
    }}
    """

    BINDINGS = [
        Binding("a", "toggle_aggressive", "aggressive", show=True),
        Binding("h", "toggle_hash_rename", "hash-rename", show=True),
        Binding("w", "toggle_dry_run", "write", show=True),
        Binding("escape", "leave", "back", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.aggressive = False
        self.hash_rename = False
        self.dry_run = True  # safe default in the TUI; w toggles to write
        self._diff: DiffTable | None = None
        self._status: Static | None = None

    def compose(self) -> ComposeResult:
        prompt_glyph = theme.glyph("prompt")
        with Vertical():
            yield Static("STRIP -- metadata laundry", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            yield Static(f" supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
                         classes="status")
            yield Input(placeholder=f"{prompt_glyph} path/to/file ...",
                        id="path-input")
            self._status = Static("", classes="status")
            yield self._status
            self._diff = DiffTable([], id="diff")
            yield self._diff
            yield Static(" ")
            yield Static(self._mode_line(), classes="status", id="modes")

    def _mode_line(self) -> str:
        on = theme.glyph("active")
        off = theme.glyph("off")
        return (
            f"  [a] aggressive {on if self.aggressive else off}   "
            f"[h] hash-rename {on if self.hash_rename else off}   "
            f"[w] write       {off if self.dry_run else on}   "
            f"[Esc] back"
        )

    # ------- actions -------------------------------------------------------

    def action_toggle_aggressive(self) -> None:
        self.aggressive = not self.aggressive
        self._refresh_modes()

    def action_toggle_hash_rename(self) -> None:
        self.hash_rename = not self.hash_rename
        self._refresh_modes()

    def action_toggle_dry_run(self) -> None:
        self.dry_run = not self.dry_run
        self._refresh_modes()

    def action_leave(self) -> None:
        # In-chrome path: hand control back to the menu without
        # killing the rest of the suite.  Legacy `babel strip` CLI
        # path still has only the standalone StripApp running, so
        # falls through to exit().
        leave = getattr(self.app, "leave_tool", None)
        if callable(leave):
            leave(self)
        else:
            self.app.exit()

    def _refresh_modes(self) -> None:
        widget = self.query_one("#modes", Static)
        widget.update(self._mode_line())

    # ------- input handling ------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip().strip('"').strip("'")
        if not raw:
            return
        path = Path(raw).expanduser()
        if not path.exists():
            self._set_status(f"no such path: {path}", "err")
            return
        if not path.is_file():
            self._set_status("path is a directory; use the CLI --batch", "warn")
            return

        try:
            outcome = strip_path(
                path,
                aggressive=self.aggressive,
                dry_run=self.dry_run,
                hash_rename=self.hash_rename,
            )
        except EncryptedPDFError as e:
            self._set_status(f"encrypted PDF: {e}", "err")
            return
        except Exception as e:
            self._set_status(f"{type(e).__name__}: {e}", "err")
            return

        if outcome.error:
            self._set_status(outcome.error, "err")
            return
        if outcome.result is None:
            self._set_status("nothing to do", "warn")
            return

        if self._diff is not None:
            self._diff.set_rows(outcome.result.removed)

        verb = "would write" if self.dry_run else "wrote"
        self._set_status(
            f"{verb} {outcome.dst}  "
            f"({outcome.size_before} -> {outcome.size_after} bytes, "
            f"{len(outcome.result.removed)} fields removed)",
            "" if outcome.result.removed else "warn",
        )

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


class StripApp(App):
    """Standalone Textual app for STRIP (Phase 2 hand-off pattern).

    When STRIP later moves fully inside the chrome (post-1.0), the
    chrome will instantiate ``StripView`` directly via
    ``push_view``; this app shell goes away.
    """

    CSS = ""
    TITLE = "TOWER OF BABEL / STRIP"

    BINDINGS = [
        Binding("ctrl+c", "quit", "quit", show=False, priority=True),
        Binding("ctrl+q", "quit", "quit", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield StripView()
        yield Footer()


def run() -> None:
    StripApp().run()


__all__ = ["StripView", "StripApp", "run"]
