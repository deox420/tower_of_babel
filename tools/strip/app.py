"""STRIP in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `StripApp(App)` wrapper that was launched
via `babel strip`; that wrapper is gone in v2.0.0 — the menu is the
single entry into STRIP. See docs/V2_REDESIGN.md §7.2.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static

from babel import art, theme
from babel.art import BABEL_TAGLINE
from babel.views import ToolHomeView
from shared.ui.diff_view import DiffTable
from tools.strip.core.pdf import EncryptedPDFError
from tools.strip.pipeline import SUPPORTED_EXTENSIONS, strip_path


class StripView(ToolHomeView):
    """STRIP's interactive home view."""

    name: ClassVar[str] = "STRIP"
    flavour: ClassVar[str] = "ACTION"
    logo: ClassVar[str] = art.STRIP_LOGO
    summary: ClassVar[str] = (
        "Metadata laundry. Removes EXIF / XMP / IPTC, PNG text chunks, "
        "PDF /Info + /Metadata, DOCX core/app/custom props, MP3 ID3 + APE."
    )
    cli_examples: ClassVar[list[tuple[str, str]]] = []
    threat_note: ClassVar[str] = ""

    DEFAULT_CSS = f"""
    StripView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
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
        Binding("escape", "leave", "back", show=True, priority=True),
        Binding("alt+0",  "leave", "menu", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.aggressive = False
        self.hash_rename = False
        self.dry_run = True
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

    # ------- actions ----------------------------------------------------

    def action_toggle_aggressive(self) -> None:
        self.aggressive = not self.aggressive
        self._refresh_modes()

    def action_toggle_hash_rename(self) -> None:
        self.hash_rename = not self.hash_rename
        self._refresh_modes()

    def action_toggle_dry_run(self) -> None:
        self.dry_run = not self.dry_run
        self._refresh_modes()

    def _refresh_modes(self) -> None:
        widget = self.query_one("#modes", Static)
        widget.update(self._mode_line())

    # ------- input handling ---------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip().strip('"').strip("'")
        if not raw:
            return
        path = Path(raw).expanduser()
        if not path.exists():
            self._set_status(f"no such path: {path}", "err")
            return
        if not path.is_file():
            self._set_status("path is a directory; use `babel --exec strip --batch ...`",
                             "warn")
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


__all__ = ["StripView"]
