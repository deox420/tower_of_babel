"""MASK in-chrome interactive view.

Lives in `babel.shell.ChromeApp`'s content slot. Pre-v2 this module
also hosted a standalone `MaskApp(App)` wrapper; that wrapper is
gone in v2.0.0 — the menu is now the single entry into MASK. See
docs/V2_REDESIGN.md §7.1.

v2.0.x polish #2 (this revision):
- Fix the "empty mask above the real mask" bug. The avatar slot
  is now hidden by default and only appears when the user presses
  [v]iew, so it can't render as an empty block between the
  identity and the share-URL.
- Add explicit section labels (IDENTITY / SHARE URL) and an
  explanation of what mask:// is for, so the two visible blocks
  are obviously different things.
- Add locale and profile cycle Buttons (used to be keys-only).
- Add a [ Vault ] button that opens MaskVaultView — that's the
  "make profiles reproducible / access the inbox later" flow.
"""
from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Input, Static

from babel import art, theme
from babel.art import BABEL_TAGLINE
from babel.vault import ArtifactKind
from babel.views import ToolHomeView
from shared.ui.step_indicator import Step, render_steps

from tools.mask.alias import LOCALES, PROFILES
from tools.mask.bundle import (
    Identity, MalformedBlob, WrongPassphrase,
    import_blob, passphrase_as_secure,
)
from tools.mask.avatar import block_preview
from tools.mask.link import build as mask_build
from tools.mask.link import parse as mask_parse
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
    MaskView .section-label {{
        color: {theme.GREEN};
        text-style: bold;
        margin-top: 1;
    }}
    MaskView .section-label.url {{
        color: {theme.CYAN};
    }}
    MaskView .url {{ color: {theme.CYAN}; }}
    MaskView .url-hint {{
        color: {theme.MUTE};
        text-style: dim italic;
    }}
    MaskView #mask-button-row {{
        height: auto;
        width: 100%;
        margin-top: 1;
    }}
    MaskView #mask-toggle-row {{
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }}
    MaskView #mask-restore-row {{
        height: auto;
        width: 100%;
        margin-bottom: 1;
    }}
    MaskView #mask-button-row Button,
    MaskView #mask-toggle-row Button,
    MaskView #mask-restore-row Button {{
        margin-right: 1;
    }}
    """

    BINDINGS = [
        Binding("enter", "new",     "generate", show=True, priority=True),
        Binding("n", "new",         "new",     show=True),
        Binding("l", "cycle_locale", "locale",  show=True),
        Binding("p", "cycle_profile", "profile", show=True),
        Binding("t", "toggle_tor",  "tor",     show=True),
        Binding("m", "toggle_mail", "mail",    show=True),
        Binding("v", "view_avatar", "view",    show=True),
        Binding("c", "copy",        "copy",    show=True),
        Binding("s", "save_vault",  "save",    show=True),
        Binding("d", "reveal_decode", "decode", show=True),
        Binding("i", "reveal_import", "import", show=True),
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
        self._identity_label: Static | None = None
        self._identity_widget: Static | None = None
        self._avatar_widget: Static | None = None
        self._url_label: Static | None = None
        self._url_widget: Static | None = None
        self._url_hint: Static | None = None
        self._tor_button: Button | None = None
        self._mail_button: Button | None = None
        self._locale_button: Button | None = None
        self._profile_button: Button | None = None
        self._inbox_button: Button | None = None
        self._decode_input: Input | None = None
        self._import_path_input: Input | None = None
        self._import_pass_input: Input | None = None
        self._busy = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("MASK -- disposable identity", classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            self._mode_line = Static(self._mode_text(), classes="status")
            yield self._mode_line
            with Horizontal(id="mask-button-row"):
                yield Button("[ Generate ]", id="mask-generate",
                             variant="success")
                self._tor_button = Button(self._tor_label(), id="mask-tor",
                                          variant=self._tor_variant())
                yield self._tor_button
                self._mail_button = Button(self._mail_label(), id="mask-mail")
                yield self._mail_button
            with Horizontal(id="mask-toggle-row"):
                self._locale_button = Button(self._locale_label(),
                                             id="mask-locale")
                yield self._locale_button
                self._profile_button = Button(self._profile_label(),
                                              id="mask-profile")
                yield self._profile_button
                yield Button("[ Save identity to Vault ]", id="mask-save",
                             variant="primary")
                yield Button("[ Vault ]", id="mask-vault")
                self._inbox_button = Button("[ Open inbox ]",
                                            id="mask-inbox")
                self._inbox_button.display = False
                yield self._inbox_button

            # RESTORE row: bring the CLI's `decode` / `import` into the TUI.
            with Horizontal(id="mask-restore-row"):
                yield Button("[ Decode mask:// ]", id="mask-decode-btn")
                yield Button("[ Import blob ]", id="mask-import-btn")
            self._decode_input = Input(
                placeholder="mask://…  (Enter to decode)", id="mask-decode-url")
            self._decode_input.display = False
            yield self._decode_input
            self._import_path_input = Input(
                placeholder="path to exported .blob", id="mask-import-path")
            self._import_path_input.display = False
            yield self._import_path_input
            self._import_pass_input = Input(
                placeholder="passphrase  (Enter to import)", password=True,
                id="mask-import-pass")
            self._import_pass_input.display = False
            yield self._import_pass_input

            # IDENTITY section
            self._identity_label = Static("  IDENTITY",
                                          classes="section-label")
            self._identity_label.display = False
            yield self._identity_label
            self._identity_widget = Static(
                "  (click [ Generate ] or press Enter)",
                classes="field",
            )
            yield self._identity_widget

            # Avatar — hidden until [v]iew. Hiding it (rather than
            # leaving it as Static("")) is the fix for the "empty
            # mask above the real one" report: an empty Static
            # between two filled blocks reads as a third (empty)
            # block.
            self._avatar_widget = Static("", classes="field")
            self._avatar_widget.display = False
            yield self._avatar_widget

            # SHARE URL section
            self._url_label = Static("  SHARE URL (mask://)",
                                     classes="section-label url")
            self._url_label.display = False
            yield self._url_label
            self._url_widget = Static("", classes="url")
            yield self._url_widget
            self._url_hint = Static(
                "  paste a mask:// URL anywhere to restore this "
                "whole identity (handle + bio + mail + inbox URL).",
                classes="url-hint",
            )
            self._url_hint.display = False
            yield self._url_hint

            yield Static(" ")
            self._steps_widget = Static("", classes="status")
            yield self._steps_widget
            self._status = Static("", classes="status")
            yield self._status
            yield Static(" ")
            yield Static(
                "  Enter/[n] new  [l] locale  [p] profile  [t] tor  "
                "[m] mail  [v] view  [c] copy  [s] save  [d] decode  "
                "[i] import  [Esc] back",
                classes="status",
            )

    # ----- button label helpers ----------------------------------------

    def _tor_label(self) -> str:
        return "[ Tor: on ]" if self.opts.use_tor else "[ Tor: CLEARNET ]"

    def _tor_variant(self) -> str:
        return "default" if self.opts.use_tor else "warning"

    def _mail_label(self) -> str:
        return "[ Mail: on ]" if self.opts.fetch_mail else "[ Mail: off ]"

    def _locale_label(self) -> str:
        return f"[ Locale: {self.opts.locale} ]"

    def _profile_label(self) -> str:
        return f"[ Profile: {self.opts.profile} ]"

    def _refresh_action_buttons(self) -> None:
        if self._tor_button is not None:
            self._tor_button.label = self._tor_label()
            self._tor_button.variant = self._tor_variant()
        if self._mail_button is not None:
            self._mail_button.label = self._mail_label()
        if self._locale_button is not None:
            self._locale_button.label = self._locale_label()
        if self._profile_button is not None:
            self._profile_button.label = self._profile_label()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "mask-generate":
            self.action_new()
        elif bid == "mask-tor":
            self.action_toggle_tor()
        elif bid == "mask-mail":
            self.action_toggle_mail()
        elif bid == "mask-locale":
            self.action_cycle_locale()
        elif bid == "mask-profile":
            self.action_cycle_profile()
        elif bid == "mask-save":
            self.action_save_vault()
        elif bid == "mask-vault":
            self.action_open_vault()
        elif bid == "mask-inbox":
            self.action_open_inbox()
        elif bid == "mask-decode-btn":
            self._reveal_decode()
        elif bid == "mask-import-btn":
            self._reveal_import()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        iid = event.input.id or ""
        if iid == "mask-decode-url":
            self._decode_url(event.value.strip())
        elif iid in ("mask-import-path", "mask-import-pass"):
            self._import_blob_file()

    # ----- decode / import (the CLI's `decode` / `import`, in-chrome) ----

    def action_reveal_decode(self) -> None:
        self._reveal_decode()

    def action_reveal_import(self) -> None:
        self._reveal_import()

    def _reveal_decode(self) -> None:
        if self._decode_input is None:
            return
        if self._import_path_input is not None:
            self._import_path_input.display = False
        if self._import_pass_input is not None:
            self._import_pass_input.display = False
        self._decode_input.display = True
        self._decode_input.value = ""
        try:
            self._decode_input.focus()
        except Exception:
            pass
        self._set_status("paste a mask:// URL and press Enter to decode", "")

    def _reveal_import(self) -> None:
        if self._import_path_input is None or self._import_pass_input is None:
            return
        if self._decode_input is not None:
            self._decode_input.display = False
        self._import_path_input.display = True
        self._import_pass_input.display = True
        self._import_path_input.value = ""
        self._import_pass_input.value = ""
        try:
            self._import_path_input.focus()
        except Exception:
            pass
        self._set_status(
            "give the exported blob path + its passphrase, then press Enter", "")

    def _decode_url(self, url: str) -> None:
        if not url:
            self._set_status("no mask:// URL given", "err")
            return
        try:
            identity = mask_parse(url)
        except Exception as e:
            self._set_status(f"decode failed: {type(e).__name__}: {e}", "err")
            return
        if self._decode_input is not None:
            self._decode_input.display = False
        self._adopt_identity(identity, "decoded mask:// URL")

    def _import_blob_file(self) -> None:
        if self._import_path_input is None or self._import_pass_input is None:
            return
        path = self._import_path_input.value.strip()
        pw = self._import_pass_input.value
        if not path:
            self._set_status("give the path to an exported blob", "err")
            return
        if not pw:
            self._set_status("a passphrase is required to import", "err")
            return
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except OSError as e:
            self._set_status(f"cannot read {path}: {e.strerror or e}", "err")
            return
        try:
            with passphrase_as_secure(pw.encode("utf-8")) as secure_pw:
                identity = import_blob(blob, secure_pw)
        except WrongPassphrase:
            self._set_status("wrong passphrase or tampered blob", "err")
            return
        except MalformedBlob as e:
            self._set_status(f"not a MASK blob: {e}", "err")
            return
        except Exception as e:
            self._set_status(f"import failed: {type(e).__name__}: {e}", "err")
            return
        finally:
            # Don't leave the passphrase sitting in the Input widget.
            self._import_pass_input.value = ""
        self._import_path_input.display = False
        self._import_pass_input.display = False
        self._adopt_identity(identity, f"imported {identity.alias.handle}")

    # ----- header -----------------------------------------------------

    def _mode_text(self) -> str:
        tor = "tor" if self.opts.use_tor else "CLEARNET"
        mail = "on" if self.opts.fetch_mail else "off"
        return (f"  locale={self.opts.locale}  profile={self.opts.profile}  "
                f"net={tor}  mail={mail}")

    def _refresh_mode(self) -> None:
        if self._mode_line is not None:
            self._mode_line.update(self._mode_text())

    # ----- actions ------------------------------------------------------

    def action_cycle_locale(self) -> None:
        i = (LOCALES.index(self.opts.locale) + 1) % len(LOCALES)
        self.opts.locale = LOCALES[i]
        self._refresh_mode()
        self._refresh_action_buttons()

    def action_cycle_profile(self) -> None:
        i = (PROFILES.index(self.opts.profile) + 1) % len(PROFILES)
        self.opts.profile = PROFILES[i]
        self._refresh_mode()
        self._refresh_action_buttons()

    def action_toggle_tor(self) -> None:
        if self.opts.use_tor:
            self._set_status(
                "clearnet bypass: Tor will NOT be used. press [t] again to revert.",
                "err",
            )
        self.opts.use_tor = not self.opts.use_tor
        self._refresh_mode()
        self._refresh_action_buttons()

    def action_toggle_mail(self) -> None:
        self.opts.fetch_mail = not self.opts.fetch_mail
        self._refresh_mode()
        self._refresh_action_buttons()

    def action_leave(self) -> None:
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
            self._avatar_widget.display = True

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

        Stored as ``ArtifactKind.IDENTITY`` with the handle as the
        fingerprint and the mask:// URL as the payload. That URL is
        complete: ``mask_parse`` reconstructs the full Identity
        (alias, bio, mail handle, inbox URL), which is what makes
        the saved profile "reproducible".
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
        try:
            vault.put(
                ArtifactKind.IDENTITY,
                label=f"{a.given} {a.family}",
                fingerprint=a.handle,
                payload=url.encode("utf-8"),
            )
        except Exception as e:
            self._set_status(f"save failed: {type(e).__name__}: {e}", "err")
            return
        self._set_status(
            f"saved to vault as {a.handle!s} ({len(vault)} item(s))", ""
        )

    def action_open_vault(self) -> None:
        """Swap the content slot to MaskVaultView."""
        vault_view = MaskVaultView(on_restore=self._restore_identity)
        # Mount it inside our Vertical so [ Esc ] returns here.
        try:
            self.mount(vault_view)
            vault_view.focus()
        except Exception as e:
            self._set_status(
                f"vault view failed to mount: {type(e).__name__}: {e}",
                "err",
            )

    def action_open_inbox(self) -> None:
        """Copy the current identity's inbox URL to the clipboard."""
        if self.identity is None or self.identity.mail is None:
            self._set_status("no mail handle on this identity", "warn")
            return
        inbox = self.identity.mail.inbox_url
        if not inbox:
            self._set_status(
                "this identity has a mail address but no inbox URL "
                "(provider didn't return one)",
                "warn",
            )
            return
        try:
            import pyperclip   # type: ignore
            pyperclip.copy(inbox)
            self._set_status(f"inbox URL copied: {inbox}", "")
        except Exception:
            self._set_status(f"copy unavailable; inbox URL: {inbox}", "warn")

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
        has_inbox = False
        if self.identity.mail is not None:
            lines.append(f"  mail     {self.identity.mail.address} "
                         f"({self.identity.mail.provider})")
            if self.identity.mail.inbox_url:
                lines.append(f"           inbox: {self.identity.mail.inbox_url}")
                has_inbox = True
        else:
            lines.append("  mail     (none)")
        self._identity_widget.update("\n".join(lines))

        # Reveal the IDENTITY label now that we have something to label.
        if self._identity_label is not None:
            self._identity_label.display = True

        # Reveal the SHARE URL section.
        if self._url_label is not None:
            self._url_label.display = True
        if self._url_widget is not None:
            self._url_widget.update(f"  {mask_build(self.identity)}")
        if self._url_hint is not None:
            self._url_hint.display = True

        # Show [ Open inbox ] only when there's actually an inbox URL.
        if self._inbox_button is not None:
            self._inbox_button.display = has_inbox

    def _restore_identity(self, url: str) -> None:
        """Callback from MaskVaultView: load a stored mask:// URL."""
        try:
            identity = mask_parse(url)
        except Exception as e:
            self._set_status(
                f"restore failed: {type(e).__name__}: {e}", "err",
            )
            return
        self._adopt_identity(
            identity, f"restored {identity.alias.handle} from vault")

    def _adopt_identity(self, identity: Identity, source: str) -> None:
        """Make ``identity`` the current one and refresh the whole view.

        Shared by the vault restore, the mask:// decoder, and the
        encrypted-blob importer so they all sync opts, re-render, and
        zeroize the previous identity identically.
        """
        if self.identity is not None:
            try:
                self.identity.zeroize()
            except Exception:
                pass
        self.identity = identity
        # Sync opts so the cycle buttons stay in sync.
        self.opts.locale = identity.alias.locale
        self.opts.profile = identity.alias.profile
        self._refresh_mode()
        self._refresh_action_buttons()
        self._render_identity()
        self._set_status(source, "")

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


class MaskVaultView(Container):
    """List of stored IDENTITY artifacts with restore/delete actions.

    Mounted into MaskView when the user clicks [ Vault ]. Reading
    the artifact payload returns the original mask:// URL, which
    :func:`mask_parse` turns back into a full Identity. That's the
    "reproducible profile with mail" flow: the mail address +
    inbox URL + credentials all survive because they're encoded
    into the URL.
    """

    DEFAULT_CSS = f"""
    MaskVaultView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: auto;
        width: 100%;
        padding: 1 2;
        border: solid {theme.GREEN_DEEP};
        margin-top: 1;
    }}
    MaskVaultView .title {{
        color: {theme.CYAN};
        text-style: bold;
    }}
    MaskVaultView .row {{
        height: auto;
        width: 100%;
        margin-top: 1;
    }}
    MaskVaultView .row Button {{ margin-right: 1; }}
    MaskVaultView .empty {{
        color: {theme.MUTE};
        text-style: dim italic;
    }}
    MaskVaultView .status {{ color: {theme.MUTE}; }}
    MaskVaultView .status.err {{ color: {theme.RED}; }}
    """

    BINDINGS = [
        Binding("escape", "close", "back", show=True, priority=True),
    ]

    can_focus = True

    def __init__(self, on_restore) -> None:
        super().__init__()
        self._on_restore = on_restore
        self._status: Static | None = None
        self._rows_container: Vertical | None = None

    def compose(self) -> ComposeResult:
        yield Static("VAULT — stored identities", classes="title")
        yield Static(
            "  click [ Restore ] to load an identity back into MASK. "
            "[ Inbox ] copies its mail inbox URL. [ Delete ] removes it.",
            classes="status",
        )
        self._rows_container = Vertical(id="vault-rows")
        yield self._rows_container
        self._status = Static("", classes="status")
        yield self._status
        yield Button("[ Close ]", id="vault-close")

    def on_mount(self) -> None:
        self._refresh_rows()
        try:
            self.focus()
        except Exception:
            pass

    def _refresh_rows(self) -> None:
        if self._rows_container is None:
            return
        # Wipe + re-render. Cheap for the row counts we expect (<<100).
        for child in list(self._rows_container.children):
            child.remove()

        vault = getattr(self.app, "vault", None)
        if vault is None:
            self._rows_container.mount(Static(
                "  (vault unavailable)", classes="empty",
            ))
            return

        artifacts = vault.list(kind=ArtifactKind.IDENTITY)
        if not artifacts:
            self._rows_container.mount(Static(
                "  (no identities saved yet — generate one and press "
                "[ Save identity to Vault ])",
                classes="empty",
            ))
            return

        for artifact in artifacts:
            line = Static(
                f"  {artifact.label}  ·  handle={artifact.fingerprint}",
                classes="field",
            )
            self._rows_container.mount(line)
            row = Horizontal(classes="row")
            self._rows_container.mount(row)
            row.mount(Button("[ Restore ]",
                             id=f"vault-restore-{artifact.fingerprint}",
                             variant="success"))
            row.mount(Button("[ Inbox ]",
                             id=f"vault-inbox-{artifact.fingerprint}"))
            row.mount(Button("[ Delete ]",
                             id=f"vault-delete-{artifact.fingerprint}",
                             variant="error"))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "vault-close":
            self.action_close()
            return

        vault = getattr(self.app, "vault", None)
        if vault is None:
            self._set_status("vault unavailable", "err")
            return

        if bid.startswith("vault-restore-"):
            fp = bid[len("vault-restore-"):]
            artifact = vault.get(fp)
            if artifact is None:
                self._set_status("artifact not found", "err")
                return
            url = artifact.payload_bytes().decode("utf-8", errors="replace")
            self._on_restore(url)
            self.action_close()
        elif bid.startswith("vault-inbox-"):
            fp = bid[len("vault-inbox-"):]
            artifact = vault.get(fp)
            if artifact is None:
                self._set_status("artifact not found", "err")
                return
            url = artifact.payload_bytes().decode("utf-8", errors="replace")
            try:
                identity = mask_parse(url)
            except Exception as e:
                self._set_status(f"parse failed: {e}", "err")
                return
            if identity.mail is None or not identity.mail.inbox_url:
                self._set_status("this identity has no inbox URL", "err")
                return
            try:
                import pyperclip  # type: ignore
                pyperclip.copy(identity.mail.inbox_url)
                self._set_status(
                    f"inbox URL copied: {identity.mail.inbox_url}", ""
                )
            except Exception:
                self._set_status(
                    f"inbox URL: {identity.mail.inbox_url}", "",
                )
        elif bid.startswith("vault-delete-"):
            fp = bid[len("vault-delete-"):]
            try:
                vault.drop(fp)
            except Exception as e:
                self._set_status(f"delete failed: {e}", "err")
                return
            self._set_status(f"deleted {fp}", "")
            self._refresh_rows()

    def action_close(self) -> None:
        try:
            self.remove()
        except Exception:
            pass

    def _set_status(self, text: str, cls: str) -> None:
        if self._status is None:
            return
        self._status.update(text)
        self._status.set_classes(f"status {cls}".strip())


__all__ = ["MaskView", "MaskVaultView"]
