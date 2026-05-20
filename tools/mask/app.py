"""MASK in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `MaskApp(App)` wrapper that was launched via
`babel mask`; that wrapper is gone in v2.0.0 — the menu is now the
single entry into MASK. See docs/V2_REDESIGN.md §7.1.

Toggles for locale / profile / Tor / mail; `n` to generate; `c` to
copy the resulting mask:// URL; `v` to render the avatar block
preview; `s` to save the identity to the suite Vault so VOID can
pick it from its lobby dropdown.
"""
from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Static

from babel import art, theme
from babel.art import BABEL_TAGLINE
from babel.vault import ArtifactKind
from babel.views import ToolHomeView
from shared.ui.step_indicator import Step, render_steps

from tools.mask.alias import LOCALES, PROFILES
from tools.mask.bundle import (
    Identity, export_blob, passphrase_as_secure,
)
from tools.mask.avatar import block_preview
from tools.mask.link import build as mask_build
from tools.mask.mail import MailUnavailable, TorRequired
from tools.mask.pipeline import (
    GenerateOpts, generate_identity, initial_steps,
)


class MaskView(ToolHomeView):
    """Interactive MASK home view, mounted by the chrome on entry."""

    name: ClassVar[str] = "MASK"
    flavour: ClassVar[str] = "ACTION"
    logo: ClassVar[str] = art.MASK_LOGO
    summary: ClassVar[str] = (
        "Disposable identity generator. Alias from a public-domain "
        "census-frequency catalog, deterministic geometric avatar, "
        "2-3 line bio, optional temp-mail handle over Tor."
    )
    cli_examples: ClassVar[list[tuple[str, str]]] = []
    threat_note: ClassVar[str] = ""

    DEFAULT_CSS = f"""
    MaskView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    MaskView .title {{ color: {theme.GREEN}; text-style: bold; }}
    MaskView .tagline {{ color: {theme.CYAN}; text-style: dim italic; }}
    MaskView .status {{ color: {theme.MUTE}; }}
    MaskView .status.warn {{ color: {theme.AMBER}; }}
    MaskView .status.err {{ color: {theme.RED}; }}
    MaskView .field {{ color: {theme.GREEN}; }}
    MaskView .url {{ color: {theme.CYAN}; }}
    """

    BINDINGS = [
        Binding("n", "new",         "new",     show=True),
        Binding("l", "cycle_locale", "locale",  show=True),
        Binding("p", "cycle_profile", "profile", show=True),
        Binding("t", "toggle_tor",  "tor",     show=True),
        Binding("m", "toggle_mail", "mail",    show=True),
        Binding("v", "view_avatar", "view",    show=True),
        Binding("c", "copy",        "copy",    show=True),
        Binding("s", "save_vault",  "save",    show=True),
        Binding("escape", "leave",  "back",    show=True, priority=True),
        Binding("alt+0",  "leave",  "menu",    show=False, priority=True),
        Binding("q", "leave",       "quit",    show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.opts = GenerateOpts()
        self.identity: Identity | None = None
        self._status: Static | None = None
        self._mode_line: Static | None = None
        self._steps_widget: Static | None = None
        self._identity_widget: Static | None = None
        self._avatar_widget: Static | None = None
        self._url_widget: Static | None = None
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("MASK -- disposable identity", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            self._mode_line = Static(self._mode_text(), classes="status")
            yield self._mode_line
            yield Static(" ")
            self._identity_widget = Static("  (press [n] to generate)",
                                           classes="field")
            yield self._identity_widget
            self._avatar_widget = Static("", classes="field")
            yield self._avatar_widget
            self._url_widget = Static("", classes="url")
            yield self._url_widget
            yield Static(" ")
            self._steps_widget = Static("", classes="status")
            yield self._steps_widget
            self._status = Static("", classes="status")
            yield self._status
            yield Static(" ")
            yield Static(
                "  [n] new  [l] locale  [p] profile  [t] tor  "
                "[m] mail  [v] view  [c] copy  [s] save  [Esc] back",
                classes="status",
            )

    # ----- header -----------------------------------------------------

    def _mode_text(self) -> str:
        tor = "tor" if self.opts.use_tor else "CLEARNET"
        mail = "on" if self.opts.fetch_mail else "off"
        return (f"  locale={self.opts.locale}  profile={self.opts.profile}  "
                f"net={tor}  mail={mail}")

    def _refresh_mode(self) -> None:
        if self._mode_line is not None:
            self._mode_line.update(self._mode_text())

    # ----- key handlers ------------------------------------------------

    def action_cycle_locale(self) -> None:
        i = (LOCALES.index(self.opts.locale) + 1) % len(LOCALES)
        self.opts.locale = LOCALES[i]
        self._refresh_mode()

    def action_cycle_profile(self) -> None:
        i = (PROFILES.index(self.opts.profile) + 1) % len(PROFILES)
        self.opts.profile = PROFILES[i]
        self._refresh_mode()

    def action_toggle_tor(self) -> None:
        if self.opts.use_tor:
            self._set_status(
                "clearnet bypass: Tor will NOT be used. press [t] again to revert.",
                "err",
            )
        self.opts.use_tor = not self.opts.use_tor
        self._refresh_mode()

    def action_toggle_mail(self) -> None:
        self.opts.fetch_mail = not self.opts.fetch_mail
        self._refresh_mode()

    def action_leave(self) -> None:
        # Best-effort scrub before handing control back to the chrome.
        if self.identity is not None:
            self.identity.zeroize()
            self.identity = None
        super().action_leave()

    async def purge_local(self) -> None:
        """Called by ChromeApp.action_purge_quit on suite exit."""
        if self.identity is not None:
            try:
                self.identity.zeroize()
            except Exception:
                pass
            self.identity = None

    def action_view_avatar(self) -> None:
        if self.identity is None:
            self._set_status("no identity yet -- press [n] first", "warn")
            return
        preview = block_preview(self.identity.alias.handle.encode("utf-8"))
        if self._avatar_widget is not None:
            self._avatar_widget.update(preview)

    def action_copy(self) -> None:
        if self.identity is None:
            self._set_status("no identity yet -- press [n] first", "warn")
            return
        url = mask_build(self.identity)
        try:
            import pyperclip   # type: ignore
            pyperclip.copy(url)
            self._set_status("mask:// copied to clipboard", "")
        except Exception:
            self._set_status("pyperclip unavailable -- URL printed above", "")
            if self._url_widget is not None:
                self._url_widget.update(url)

    def action_save_vault(self) -> None:
        """Push the current identity to the suite Vault.

        Stored as ``ArtifactKind.IDENTITY`` with the handle as label
        and the Ed25519 fingerprint as key. VOID's lobby reads this
        list to populate its identity dropdown (see V2_REDESIGN §3.3).
        """
        if self.identity is None:
            self._set_status("no identity yet -- press [n] first", "warn")
            return
        vault = getattr(self.app, "vault", None)
        if vault is None:
            self._set_status("vault unavailable", "warn")
            return
        a = self.identity.alias
        try:
            url = mask_build(self.identity)
        except Exception as e:
            self._set_status(f"save failed: {type(e).__name__}: {e}", "err")
            return
        fingerprint = a.handle
        try:
            vault.put(
                ArtifactKind.IDENTITY,
                label=f"{a.given} {a.family}",
                fingerprint=fingerprint,
                payload=url.encode("utf-8"),
            )
        except Exception as e:
            self._set_status(f"save failed: {type(e).__name__}: {e}", "err")
            return
        self._set_status(
            f"saved to vault as {fingerprint!s} ({len(vault)} item(s))", ""
        )

    def action_new(self) -> None:
        if self._busy:
            return
        self.run_worker(self._generate(), exclusive=True)

    # ----- worker -------------------------------------------------------

    async def _generate(self) -> None:
        self._busy = True
        steps = initial_steps(self.opts)
        if self._steps_widget is not None:
            self._steps_widget.update(render_steps(steps))

        def on_step(i: int, step: Step) -> None:
            steps[i] = step
            if self._steps_widget is not None:
                self._steps_widget.update(render_steps(steps))

        try:
            self.identity = await generate_identity(self.opts, on_step)
        except TorRequired as e:
            self._set_status(f"Tor required: {e}", "err")
            self._busy = False
            return
        except MailUnavailable as e:
            self._set_status(f"mail unavailable: {e}", "err")
            self._busy = False
            return
        except Exception as e:
            self._set_status(f"failed: {type(e).__name__}: {e}", "err")
            self._busy = False
            return

        self._render_identity()
        self._busy = False

    def _render_identity(self) -> None:
        if self.identity is None or self._identity_widget is None:
            return
        a = self.identity.alias
        lines: list[str] = []
        lines.append(f"  alias    {a.given} {a.family} "
                     f"({a.locale}, {a.profile})")
        lines.append(f"  handle   {a.handle}")
        lines.append(f"  bio      {self.identity.bio}")
        if self.identity.mail is not None:
            lines.append(f"  mail     {self.identity.mail.address} "
                         f"({self.identity.mail.provider})")
            if self.identity.mail.inbox_url:
                lines.append(f"           inbox: {self.identity.mail.inbox_url}")
        else:
            lines.append("  mail     (none)")
        self._identity_widget.update("\n".join(lines))
        if self._url_widget is not None:
            self._url_widget.update(f"  mask://  {mask_build(self.identity)}")

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


__all__ = ["MaskView"]

