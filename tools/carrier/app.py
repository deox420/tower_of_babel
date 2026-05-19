"""CARRIER Textual screen -- minimal interactive front-end.

Mode toggles: embed (default), extract, capacity, inspect. The
screen reuses ``shared.ui.diff_view``-style verdict tables and
``shared.ui.hex_view`` for the payload preview.
"""
from __future__ import annotations

from pathlib import Path

from cryptography.exceptions import InvalidTag
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Input, Static

from babel import theme
from babel.art import BABEL_TAGLINE
from shared.ui.hex_view import HexView
from tools.carrier.capacity import PayloadTooLargeError
from tools.carrier.chisquare import chi_square
from tools.carrier.pipeline import (
    LSB_EMBEDDED_THRESHOLD, KdfParams, TamperedCoverError,
    UnsupportedCoverError, detect_format, embed_payload, extract_payload,
)
from tools.carrier.core import png as png_core
from tools.carrier.core import wav as wav_core


class CarrierView(Container):
    """Steganography -- AES-256-GCM payload hidden in PNG/WAV LSB plane.

    Mounted inside the babel chrome's content slot.  Action-flavoured:
    Esc tears the view down and returns to the menu.  No slot.
    """

    name = "CARRIER"
    flavour = "ACTION"
    can_focus = True
    service = None

    DEFAULT_CSS = f"""
    CarrierView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
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
        Binding("escape", "leave", "back", show=True),
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

    # ----- mode handling ---------------------------------------------------

    def _mode_text(self) -> str:
        glyphs = {"embed": "active", "extract": "active",
                  "capacity": "active", "inspect": "active"}
        return f"  mode: {self.mode}"

    def action_set_mode(self, mode: str) -> None:
        if mode in {"embed", "extract", "capacity", "inspect"}:
            self.mode = mode
            if self._mode_line is not None:
                self._mode_line.update(self._mode_text())

    def action_leave(self) -> None:
        leave = getattr(self.app, "leave_tool", None)
        if callable(leave):
            leave(self)
        else:
            self.app.exit()

    # ----- submit ----------------------------------------------------------

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

    # ----- per-mode --------------------------------------------------------

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

    # ----- paste-routing entry (docs/NAVIGATION.md section 6) --------------

    def prefill_link(self, url: str) -> None:
        """Open in inspect mode and surface the carrier header.

        Called by the chrome when the user pastes a ``carrier://`` URL
        in the menu's paste field.  carrier:// is a metadata-only
        scheme (MASTER.md 5.6); decoding gives the salt + nonce +
        size triple, no payload.  We display the parsed body and
        switch the view to inspect mode so the next submission
        runs a chi-square check.
        """
        from shared.link.invite import decode as decode_link
        from shared.link.invite import InvalidInvite
        try:
            link = decode_link(url)
        except InvalidInvite as e:
            self._set_status(f"invalid carrier:// link: {e}", "err")
            return
        self.mode = "inspect"
        if self._mode_line is not None:
            self._mode_line.update(self._mode_text())
        # Show the header body to the user.  Tier-1 text only.
        body = link.body
        lines = [
            f"  carrier:// header",
            f"    fmt   {body.get('fmt', '?')}",
            f"    size  {body.get('size', '?')} bytes",
            f"    nonce {len((body.get('nonce') or ''))} chars",
        ]
        self._set_status("\n".join(lines), "")


class CarrierApp(App):
    TITLE = "TOWER OF BABEL / CARRIER"
    BINDINGS = [
        Binding("ctrl+c", "quit", "quit", show=False, priority=True),
        Binding("ctrl+q", "quit", "quit", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield CarrierView()
        yield Footer()


def run() -> None:
    CarrierApp().run()


__all__ = ["CarrierView", "CarrierApp", "run"]
