"""MASK Textual screen -- minimal interactive front-end.

Toggles for locale / profile / Tor / mail; `n` to generate; `x` to
export. The screen renders the current identity (alias, handle, bio,
avatar block-preview, mail) and the per-phase step indicator below.

Mounted inside the babel chrome by ``babel.__main__._run_mask``.
The chrome owns the outer frame and the footer; this view owns the
content slot.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Input, Static

from babel import theme
from babel.art import BABEL_TAGLINE
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


class MaskView(Container):
    """Disposable identity generator -- alias, geometric avatar, bio, temp mail.

    Mounted inside the babel chrome's content slot (MASTER.md 4.4).
    Action-flavoured: pressing Esc tears the view down and returns
    to the menu.  No slot in the registry, no footer contribution.
    """

    name = "MASK"
    flavour = "ACTION"
    can_focus = True
    service = None    # ACTION views have no Service.

    DEFAULT_CSS = f"""
    MaskView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
    }}
    MaskView .title {{ color: {theme.GREEN}; text-style: bold; }}
    MaskView .tagline {{ color: {theme.CYAN}; text-style: dim italic; }}
    MaskView .status {{ color: {theme.MUTE}; }}
    MaskView .status.warn {{ color: {theme.AMBER}; }}
    MaskView .status.err {{ color: {theme.RED}; }}
    MaskView .field {{ color: {theme.GREEN}; }}
    MaskView .url {{ color: {theme.CYAN}; }}
    MaskView Input {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    """

    BINDINGS = [
        Binding("n", "new",         "new",     show=True),
        Binding("l", "cycle_locale", "locale",  show=True),
        Binding("p", "cycle_profile", "profile", show=True),
        Binding("t", "toggle_tor",  "tor",     show=True),
        Binding("m", "toggle_mail", "mail",    show=True),
        # TUI inline export deferred post-1.0; use CLI `babel mask new
        # --export PATH` for encrypted bundle export.  No `x` binding so
        # the UI does not advertise a stub action.
        Binding("v", "view_avatar", "view",    show=True),
        Binding("c", "copy",        "copy",    show=True),
        Binding("escape", "leave",  "back",    show=True),
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
                "[m] mail  [v] view  [c] copy  [Esc] back",
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
            # Going to clearnet -- show the red banner via status.
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
        # Best-effort scrub before leaving.
        if self.identity is not None:
            self.identity.zeroize()
            self.identity = None
        # When mounted inside the babel chrome (the menu path), hand
        # control back to the chrome -- it knows whether to tear us
        # down (ACTION) or background us (SERVICE).  When mounted
        # under the legacy MaskApp wrapper (the `babel mask` CLI
        # path), exit the app as before.
        leave = getattr(self.app, "leave_tool", None)
        if callable(leave):
            leave(self)
        else:
            self.app.exit()

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

    def action_new(self) -> None:
        if self._busy:
            return
        self.run_worker(self._generate(), exclusive=True)

    # action_export removed pre-1.0: the TUI prompt was a stub.  Encrypted
    # export is available via the CLI: `babel mask new --export PATH`.  A
    # full inline prompt may land post-1.0 (tracked in RELEASE_NOTES).

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

    # ----- paste-routing entry (docs/NAVIGATION.md section 6) --------------

    def prefill_link(self, url: str) -> None:
        """Open the view in decode mode and show the parsed bundle.

        Called by ``ChromeApp`` when the user pastes a ``mask://`` URL
        into the menu's paste field.  Decoding failures surface as
        a red status row; the view is still mounted (the user can
        copy/correct the URL).
        """
        from tools.mask.link import parse as mask_parse
        from shared.link.invite import InvalidInvite
        try:
            identity = mask_parse(url)
        except InvalidInvite as e:
            self._set_status(f"invalid mask:// link: {e}", "err")
            return
        self.identity = identity
        self._render_identity()
        if self._url_widget is not None:
            self._url_widget.update(f"  mask://  {url}")
        self._set_status("loaded from paste", "")


class MaskApp(App):
    TITLE = "TOWER OF BABEL / MASK"
    BINDINGS = [
        Binding("ctrl+c", "quit", "quit", show=False, priority=True),
        Binding("ctrl+q", "quit", "quit", show=False, priority=True),
    ]

    def compose(self) -> ComposeResult:
        yield MaskView()
        yield Footer()


def run() -> None:
    MaskApp().run()


__all__ = ["MaskView", "MaskApp", "run"]
