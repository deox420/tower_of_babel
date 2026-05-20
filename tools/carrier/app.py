"""CARRIER in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `CarrierApp(App)` wrapper that was launched
via `babel carrier`; that wrapper is gone in v2.0.0 — the menu is
the single entry into CARRIER. See docs/V2_REDESIGN.md §7.3.

v2.0.1 polish: each of the 4 modes (embed / extract / capacity /
inspect) is a clickable Button at the top of the view. The hint
line under the buttons explains exactly which Inputs the active
mode reads. Unused Inputs are disabled (greyed out) per mode so the
user can't accidentally type into a field that won't be read.
"""
from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from cryptography.exceptions import InvalidTag
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Input, Static

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


MODE_HINTS = {
    "embed":    "EMBED — fill cover + payload + passphrase, click [Run] or press Enter",
    "extract":  "EXTRACT — fill cover + passphrase, click [Run] or press Enter",
    "capacity": "CAPACITY — fill cover only, click [Run] or press Enter",
    "inspect":  "INSPECT — fill cover only, click [Run] or press Enter",
}


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
    CarrierView .hint {{
        color: {theme.CYAN};
        text-style: italic;
        margin-top: 1;
        margin-bottom: 1;
    }}
    CarrierView Input {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    CarrierView Input:disabled {{
        color: {theme.MUTE};
        border: tall {theme.GREEN_DEEP} 30%;
    }}
    CarrierView #mode-bar {{
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }}
    CarrierView #mode-bar Button {{ margin-right: 1; }}
    CarrierView #run-row {{
        height: auto;
        margin-top: 1;
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
        self._hint: Static | None = None
        self._hex: HexView | None = None
        self._mode_buttons: dict[str, Button] = {}
        self._cover_input: Input | None = None
        self._payload_input: Input | None = None
        self._passphrase_input: Input | None = None

    def compose(self) -> ComposeResult:
        prompt = theme.glyph("prompt")
        with Vertical():
            yield Static("CARRIER -- steganography", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            with Horizontal(id="mode-bar"):
                for mode in ("embed", "extract", "capacity", "inspect"):
                    variant = "primary" if mode == self.mode else "default"
                    btn = Button(f"[ {mode.title()} ]",
                                 id=f"carrier-mode-{mode}",
                                 variant=variant)
                    self._mode_buttons[mode] = btn
                    yield btn
            self._hint = Static(MODE_HINTS[self.mode], classes="hint")
            yield self._hint
            self._cover_input = Input(placeholder=f"{prompt} cover path ...",
                                      id="cover")
            yield self._cover_input
            self._payload_input = Input(
                placeholder=f"{prompt} payload path (embed only) ...",
                id="payload")
            yield self._payload_input
            self._passphrase_input = Input(
                placeholder=f"{prompt} passphrase ...",
                id="passphrase", password=True)
            yield self._passphrase_input
            with Horizontal(id="run-row"):
                yield Button("[ Run ]", id="carrier-run",
                             variant="success")
            self._status = Static("", classes="status")
            yield self._status
            self._hex = HexView(b"", max_rows=4, id="hex-preview")
            yield self._hex
            yield Static(
                "  [e] embed  [x] extract  [c] capacity  [i] inspect  [Esc] back",
                classes="status")
        self._sync_input_visibility()

    # ----- mode handling ------------------------------------------------

    def action_set_mode(self, mode: str) -> None:
        if mode not in MODE_HINTS:
            return
        self.mode = mode
        for name, btn in self._mode_buttons.items():
            btn.variant = "primary" if name == mode else "default"
        if self._hint is not None:
            self._hint.update(MODE_HINTS[mode])
        self._sync_input_visibility()

    def _sync_input_visibility(self) -> None:
        """Disable Inputs the active mode doesn't read."""
        needs_payload = self.mode == "embed"
        needs_passphrase = self.mode in ("embed", "extract")
        if self._payload_input is not None:
            self._payload_input.disabled = not needs_payload
        if self._passphrase_input is not None:
            self._passphrase_input.disabled = not needs_passphrase

    # ----- mouse / submit dispatch --------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("carrier-mode-"):
            self.action_set_mode(bid[len("carrier-mode-"):])
        elif bid == "carrier-run":
            self._run_current_mode()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._run_current_mode()

    def _run_current_mode(self) -> None:
        cover_path = self._cover_input.value.strip() if self._cover_input else ""
        payload_path = self._payload_input.value.strip() if self._payload_input else ""
        passphrase = self._passphrase_input.value if self._passphrase_input else ""
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
