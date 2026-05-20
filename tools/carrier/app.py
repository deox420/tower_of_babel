"""CARRIER in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `CarrierApp(App)` wrapper that was launched
via `babel carrier`; that wrapper is gone in v2.0.0 — the menu is
the single entry into CARRIER. See docs/V2_REDESIGN.md §7.3.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from cryptography.exceptions import InvalidTag
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Input, Static

from babel import art, theme
from babel.art import BABEL_TAGLINE
from babel.views import ToolHomeView
from shared.ui.hex_view import HexView
from tools.carrier.capacity import PayloadTooLargeError
from tools.carrier.chisquare import chi_square
from tools.carrier.pipeline import (
    LSB_EMBEDDED_THRESHOLD, KdfParams, TamperedCoverError,
    UnsupportedCoverError, detect_format, embed_payload, extract_payload,
)
from tools.carrier.core import png as png_core
from tools.carrier.core import wav as wav_core


class CarrierView(ToolHomeView):
    """CARRIER's interactive home view."""

    name: ClassVar[str] = "CARRIER"
    flavour: ClassVar[str] = "ACTION"
    logo: ClassVar[str] = art.CARRIER_LOGO
    summary: ClassVar[str] = (
        "Steganography. AES-256-GCM payload + Argon2id KDF hidden in "
        "the LSB plane of a PNG or WAV cover. No magic header in output."
    )
    cli_examples: ClassVar[list[tuple[str, str]]] = []
    threat_note: ClassVar[str] = ""

    DEFAULT_CSS = f"""
    CarrierView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    CarrierView .title {{ color: {theme.GREEN}; text-style: bold; }}
    CarrierView .tagline {{ color: {theme.CYAN}; text-style: dim italic; }}
    CarrierView .status {{ color: {theme.MUTE}; }}
    CarrierView .status.warn {{ color: {theme.AMBER}; }}
    CarrierView .status.err {{ color: {theme.RED}; }}
    CarrierView Input {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    """

    BINDINGS = [
        Binding("e", "set_mode('embed')",    "embed",    show=True),
        Binding("x", "set_mode('extract')",  "extract",  show=True),
        Binding("c", "set_mode('capacity')", "capacity", show=True),
        Binding("i", "set_mode('inspect')",  "inspect",  show=True),
        Binding("escape", "leave", "back", show=True, priority=True),
        Binding("alt+0",  "leave", "menu", show=False, priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.mode = "embed"
        self._status: Static | None = None
        self._mode_line: Static | None = None
        self._hex: HexView | None = None

    def compose(self) -> ComposeResult:
        prompt = theme.glyph("prompt")
        with Vertical():
            yield Static("CARRIER -- steganography", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            self._mode_line = Static(self._mode_text(), classes="status")
            yield self._mode_line
            yield Input(placeholder=f"{prompt} cover path ...", id="cover")
            yield Input(placeholder=f"{prompt} payload path "
                                    f"(embed only) ...", id="payload")
            yield Input(placeholder=f"{prompt} passphrase ...",
                        id="passphrase", password=True)
            self._status = Static("", classes="status")
            yield self._status
            self._hex = HexView(b"", max_rows=4, id="hex-preview")
            yield self._hex
            yield Static(" ")
            yield Static("  [e] embed  [x] extract  [c] capacity  "
                         "[i] inspect  [Esc] back",
                         classes="status")

    # ----- mode handling ------------------------------------------------

    def _mode_text(self) -> str:
        return f"  mode: {self.mode}"

    def action_set_mode(self, mode: str) -> None:
        if mode in {"embed", "extract", "capacity", "inspect"}:
            self.mode = mode
            if self._mode_line is not None:
                self._mode_line.update(self._mode_text())

    # ----- submit -------------------------------------------------------

    def on_input_submitted(self, event: Input.Submitted) -> None:
        cover_path = self.query_one("#cover", Input).value.strip()
        payload_path = self.query_one("#payload", Input).value.strip()
        passphrase = self.query_one("#passphrase", Input).value
        if not cover_path:
            self._set_status("cover path required", "err")
            return

        try:
            cover_bytes = Path(cover_path).expanduser().read_bytes()
        except OSError as e:
            self._set_status(f"cannot read cover: {e}", "err")
            return

        try:
            fmt = detect_format(cover_bytes)
        except UnsupportedCoverError as e:
            self._set_status(str(e), "err")
            return

        if self.mode == "capacity":
            self._do_capacity(cover_bytes, fmt)
            return
        if self.mode == "inspect":
            self._do_inspect(cover_bytes, fmt)
            return

        if not passphrase:
            self._set_status("passphrase required", "err")
            return

        if self.mode == "embed":
            self._do_embed(cover_path, cover_bytes, payload_path,
                           passphrase, fmt)
        elif self.mode == "extract":
            self._do_extract(cover_path, cover_bytes, passphrase, fmt)

    # ----- per-mode -----------------------------------------------------

    def _do_capacity(self, cover_bytes: bytes, fmt: str) -> None:
        cap = (png_core.cover_capacity(png_core.open_cover(cover_bytes))
               if fmt == "png" else
               wav_core.cover_capacity(wav_core.open_cover(cover_bytes)))
        self._set_status(
            f"{fmt}: {cap.safe_bytes} safe bytes "
            f"(of {cap.channel_bits // 8} max)", "")

    def _do_inspect(self, cover_bytes: bytes, fmt: str) -> None:
        samples = (png_core.lsb_samples(png_core.open_cover(cover_bytes))
                   if fmt == "png" else
                   wav_core.lsb_samples(wav_core.open_cover(cover_bytes)))
        res = chi_square(samples)
        warn = res.p_value > LSB_EMBEDDED_THRESHOLD
        self._set_status(
            f"chi2={res.chi2:.2f} p={res.p_value:.4f} "
            f"({'tampered' if warn else 'untampered'})",
            "warn" if warn else "")

    def _do_embed(self, cover_path: str, cover_bytes: bytes,
                  payload_path: str, passphrase: str, fmt: str) -> None:
        if not payload_path:
            self._set_status("payload path required for embed", "err")
            return
        try:
            payload_bytes = Path(payload_path).expanduser().read_bytes()
        except OSError as e:
            self._set_status(f"cannot read payload: {e}", "err")
            return

        try:
            report = embed_payload(
                cover_bytes, payload_bytes, passphrase.encode("utf-8"),
                fmt=fmt, kdf=KdfParams(),
            )
        except (PayloadTooLargeError, TamperedCoverError, ValueError) as e:
            self._set_status(str(e), "err")
            return

        out_path = Path(cover_path).expanduser()
        out_path = out_path.with_suffix(f".carrier{out_path.suffix}")
        try:
            out_path.write_bytes(report.output)
        except OSError as e:
            self._set_status(f"write failed: {e}", "err")
            return

        self._set_status(
            f"embedded {report.framed_size} bytes -> {out_path} "
            f"(p={report.chi_square.p_value:.3f})",
            "warn" if report.chi_square_warn else "")
        if self._hex is not None:
            self._hex.set_data(report.output[:64])

    def _do_extract(self, cover_path: str, cover_bytes: bytes,
                    passphrase: str, fmt: str) -> None:
        try:
            report = extract_payload(
                cover_bytes, passphrase.encode("utf-8"),
                fmt=fmt, kdf=KdfParams(),
            )
        except InvalidTag:
            self._set_status("wrong passphrase or no payload here", "err")
            return
        except ValueError as e:
            self._set_status(str(e), "err")
            return

        self._set_status(
            f"extracted {len(report.payload)} bytes "
            f"(compressed: {report.compressed})", "")
        if self._hex is not None:
            self._hex.set_data(report.payload[:64])

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


__all__ = ["CarrierView"]
