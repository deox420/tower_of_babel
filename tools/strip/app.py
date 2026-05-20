"""STRIP in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `StripApp(App)` wrapper that was launched
via `babel strip`; that wrapper is gone in v2.0.0 — the menu is the
single entry into STRIP. See docs/V2_REDESIGN.md §7.2.

v2.0.1 polish: the workflow is now scan-first. Entering a path
ALWAYS runs `strip_path(dry_run=True)` and renders a big green/red
banner answering "does this file have metadata?". If yes, the diff
table populates and a `[Write clean copy]` button appears; if no,
the button stays hidden.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

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
    StripView #strip-toggles {{
        height: auto;
        width: 100%;
        margin-top: 1;
        margin-bottom: 1;
    }}
    StripView #strip-toggles Button {{ margin-right: 1; }}
    StripView .banner {{
        width: 100%;
        height: 3;
        content-align: center middle;
        text-align: center;
        text-style: bold;
        margin-top: 1;
        margin-bottom: 1;
    }}
    StripView .banner.ok {{
        color: {theme.BG};
        background: {theme.GREEN};
    }}
    StripView .banner.bad {{
        color: {theme.BG};
        background: {theme.RED};
    }}
    StripView #diff {{
        height: 1fr;
        overflow-y: auto;
    }}
    StripView #strip-write {{
        margin-top: 1;
    }}
    """

    BINDINGS = [
        Binding("a", "toggle_aggressive", "aggressive", show=True),
        Binding("h", "toggle_hash_rename", "hash-rename", show=True),
        Binding("escape", "leave", "back", show=True, priority=True),
        Binding("alt+0",  "leave", "menu", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.aggressive = False
        self.hash_rename = False
        self._diff: DiffTable | None = None
        self._status: Static | None = None
        self._banner: Static | None = None
        self._write_button: Button | None = None
        self._aggressive_button: Button | None = None
        self._hash_button: Button | None = None
        self._last_path: Path | None = None
        self._last_has_metadata = False

    def compose(self) -> ComposeResult:
        prompt_glyph = theme.glyph("prompt")
        with Vertical():
            yield Static("STRIP -- metadata laundry", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            yield Static(f" supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
                         classes="status")
            with Horizontal(id="strip-toggles"):
                self._aggressive_button = Button(self._aggressive_label(),
                                                 id="strip-aggressive")
                yield self._aggressive_button
                self._hash_button = Button(self._hash_label(),
                                           id="strip-hash-rename")
                yield self._hash_button
            yield Input(placeholder=f"{prompt_glyph} path/to/file ... (Enter to scan)",
                        id="path-input")
            self._banner = Static("", classes="banner")
            self._banner.display = False
            yield self._banner
            self._diff = DiffTable([], id="diff")
            yield self._diff
            self._write_button = Button("[ Write clean copy ]",
                                        id="strip-write",
                                        variant="success")
            self._write_button.display = False
            yield self._write_button
            self._status = Static("", classes="status")
            yield self._status
            yield Static(" ")
            yield Static(
                "  Enter scan   [a] aggressive   [h] hash-rename   [Esc] back",
                classes="status",
            )

    def _aggressive_label(self) -> str:
        return f"[ Aggressive: {'on' if self.aggressive else 'off'} ]"

    def _hash_label(self) -> str:
        return f"[ Hash-rename: {'on' if self.hash_rename else 'off'} ]"

    # ------- actions ----------------------------------------------------

    def action_toggle_aggressive(self) -> None:
        self.aggressive = not self.aggressive
        if self._aggressive_button is not None:
            self._aggressive_button.label = self._aggressive_label()
        # Re-scan with new flag if we have a path on file.
        if self._last_path is not None:
            self._scan(self._last_path)

    def action_toggle_hash_rename(self) -> None:
        self.hash_rename = not self.hash_rename
        if self._hash_button is not None:
            self._hash_button.label = self._hash_label()

    # ------- mouse handling ---------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "strip-aggressive":
            self.action_toggle_aggressive()
        elif bid == "strip-hash-rename":
            self.action_toggle_hash_rename()
        elif bid == "strip-write":
            self._write_clean_copy()

    # ------- input handling ---------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        raw = event.value.strip().strip('"').strip("'")
        if not raw:
            return
        path = Path(raw).expanduser()
        if not path.exists():
            self._set_status(f"no such path: {path}", "err")
            self._hide_results()
            return
        if not path.is_file():
            self._set_status("path is a directory; use `babel --exec strip --batch ...`",
                             "warn")
            self._hide_results()
            return
        self._scan(path)

    # ------- scan + write -----------------------------------------------

    def _scan(self, path: Path) -> None:
        """Dry-run strip_path and render the verdict banner."""
        self._last_path = path
        try:
            outcome = strip_path(
                path,
                aggressive=self.aggressive,
                dry_run=True,
                hash_rename=self.hash_rename,
            )
        except EncryptedPDFError as e:
            self._set_status(f"encrypted PDF: {e}", "err")
            self._hide_results()
            return
        except Exception as e:
            self._set_status(f"{type(e).__name__}: {e}", "err")
            self._hide_results()
            return

        if outcome.error:
            self._set_status(outcome.error, "err")
            self._hide_results()
            return
        if outcome.result is None:
            # Format wasn't supported / file unreadable
            self._set_status("no parser for this file type", "warn")
            self._hide_results()
            return

        removed = outcome.result.removed
        self._last_has_metadata = bool(removed)

        if self._diff is not None:
            self._diff.set_rows(removed if removed else [])

        if self._banner is not None:
            if removed:
                self._banner.update(f"❌  TIENE {len(removed)} CAMPO(S) DE METADATOS")
                self._banner.set_classes("banner bad")
            else:
                self._banner.update("✅  SIN METADATOS — la imagen ya está limpia")
                self._banner.set_classes("banner ok")
            self._banner.display = True

        if self._write_button is not None:
            self._write_button.display = bool(removed)

        self._set_status(
            f"scan: {outcome.size_before} bytes, "
            f"{len(removed)} field(s) would be removed",
            "" if removed else "warn",
        )

    def _write_clean_copy(self) -> None:
        if self._last_path is None or not self._last_has_metadata:
            return
        try:
            outcome = strip_path(
                self._last_path,
                aggressive=self.aggressive,
                dry_run=False,
                hash_rename=self.hash_rename,
            )
        except Exception as e:
            self._set_status(f"write failed: {type(e).__name__}: {e}", "err")
            return
        if outcome.error:
            self._set_status(outcome.error, "err")
            return
        self._set_status(
            f"wrote {outcome.dst}  "
            f"({outcome.size_before} -> {outcome.size_after} bytes)",
            "",
        )
        # Hide the write button so the user doesn't double-write.
        if self._write_button is not None:
            self._write_button.display = False

    def _hide_results(self) -> None:
        if self._banner is not None:
            self._banner.display = False
        if self._diff is not None:
            self._diff.set_rows([])
        if self._write_button is not None:
            self._write_button.display = False

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


__all__ = ["StripView"]
