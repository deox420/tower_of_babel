"""In-chrome tool home views.

When the user picks a tool from the main menu, the chrome mounts the
corresponding ``ToolHomeView`` in its content slot.  These views are
intentionally **lightweight**: they show what the tool is, the CLI
commands that drive it, and the hotkeys to return to the menu /
background the service.  The heavy lifting (real chat, real metadata
strip, real cover-traffic engine) still lives in each tool's CLI for
v1.0; service-flavoured tools (VOID, MIRAGE) get registered in the
``ServiceRegistry`` so the user can background them with ``Alt+0``
and come back via ``Alt+N``.

Each subclass declares:

* ``name`` -- short uppercase tool name (matches the menu).
* ``flavour`` -- ``"SERVICE"`` keeps the view in a slot when the user
  returns to the menu; ``"ACTION"`` is torn down on return.
* ``logo`` -- pre-rendered ASCII banner from ``babel.art``.
* ``summary`` -- one-paragraph blurb.
* ``cli_examples`` -- list of ``(command, gloss)`` tuples.

The base class also implements the chrome's ``Service`` Protocol so
service-flavoured tools can register with the registry without any
extra boilerplate.
"""
from __future__ import annotations

from typing import ClassVar, Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widget import Widget
from textual.widgets import Static

from babel import art, theme


_FLAVOUR_LITERAL = Literal["SERVICE", "ACTION"]


class ToolHomeView(Vertical):
    """Home view for one tool, mounted inside the chrome's content slot.

    Subclasses set the class-level attrs.  The view is focusable so
    its bindings fire as soon as it's pushed (the menu had the same
    issue -- Phase 6 hotfix).
    """

    name: ClassVar[str] = "?"
    flavour: ClassVar[_FLAVOUR_LITERAL] = "ACTION"
    logo: ClassVar[str] = ""
    summary: ClassVar[str] = ""
    cli_examples: ClassVar[list[tuple[str, str]]] = []
    threat_note: ClassVar[str] = ""

    can_focus = True

    BINDINGS = [
        Binding("escape", "leave", "back to menu", show=True, priority=True),
        Binding("alt+0",  "leave", "menu",          show=False, priority=True),
    ]

    DEFAULT_CSS = f"""
    ToolHomeView {{
        align: center top;
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    ToolHomeView #tool-card {{
        height: auto;
        width: 90%;
        max-width: 100;
        padding: 1 2;
        background: {theme.BG};
    }}
    ToolHomeView .logo {{
        width: 100%;
        color: {theme.GREEN};
        text-style: bold;
        text-align: center;
        height: auto;
    }}
    ToolHomeView .flavour-tag {{
        width: 100%;
        color: {theme.AMBER};
        text-style: dim italic;
        text-align: center;
    }}
    ToolHomeView .summary {{
        width: 100%;
        color: {theme.GREEN};
        margin-top: 1;
        margin-bottom: 1;
    }}
    ToolHomeView .section {{
        width: 100%;
        color: {theme.CYAN};
        text-style: bold;
        margin-top: 1;
    }}
    ToolHomeView .cli-row {{
        width: 100%;
        color: {theme.GREEN};
    }}
    ToolHomeView .cli-gloss {{
        width: 100%;
        color: {theme.MUTE};
        text-style: dim;
    }}
    ToolHomeView .threat {{
        width: 100%;
        color: {theme.AMBER};
        text-style: italic;
        margin-top: 1;
    }}
    ToolHomeView .keys {{
        width: 100%;
        color: {theme.CYAN};
        text-style: dim;
        text-align: center;
        margin-top: 1;
    }}
    """

    def on_mount(self) -> None:
        try:
            self.focus()
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        compact = theme.is_compact()
        with Vertical(id="tool-card"):
            yield Static(self.logo, classes="logo")
            flavour_word = "service" if self.flavour == "SERVICE" else "action"
            yield Static(f"-- {self.name} ({flavour_word}) --",
                         classes="flavour-tag")
            yield Static(self.summary, classes="summary")
            if self.cli_examples:
                yield Static("Quick start (CLI):", classes="section")
                for cmd, gloss in self.cli_examples:
                    if compact:
                        yield Static(f"  {cmd}", classes="cli-row")
                        yield Static(f"    {gloss}", classes="cli-gloss")
                    else:
                        # 2-column inline layout when room permits.
                        yield Static(f"  {cmd}", classes="cli-row")
                        yield Static(f"      {gloss}", classes="cli-gloss")
            if self.threat_note:
                yield Static("Honest threat note:", classes="section")
                yield Static(self.threat_note, classes="threat")
            if self.flavour == "SERVICE":
                hint = "[Alt+0] background to slot   [Esc] return to menu"
            else:
                hint = "[Esc] return to menu"
            yield Static(hint, classes="keys")

    # ----- chrome action handlers ------------------------------------------

    def action_leave(self) -> None:
        """Esc / Alt+0 -- hand control back to the chrome.

        The chrome decides what 'leave' means based on flavour:
        * SERVICE: pop the view but keep this instance registered in
          the slot so Alt+N can bring it back.
        * ACTION: pop and discard.
        """
        app = self.app
        leave = getattr(app, "leave_tool", None)
        if callable(leave):
            leave(self)
        else:
            # Defensive fallback (e.g. running under a non-Babel app).
            ret = getattr(app, "return_to_menu", None)
            if callable(ret):
                ret()

    # ----- Service Protocol (used when flavour == "SERVICE") ---------------

    def status_line(self) -> str:
        return "idle"

    def footer_contribution(self) -> dict:
        return {}

    def resource_caps(self) -> dict:
        return {}

    async def purge_local(self) -> None:
        """Default: no in-RAM state to purge in v1.0 home views."""
        return None


# ---------------------------------------------------------------------------
# Per-tool home views
# ---------------------------------------------------------------------------


class VoidHomeView(ToolHomeView):
    name = "VOID"
    flavour = "SERVICE"
    logo = art.VOID_LOGO
    summary = (
        "Ephemeral encrypted messenger over Tor. X3DH initial AKE + "
        "Double Ratchet per-message keys. Fresh identity per session, "
        "no key material on disk, /burn wipes RAM on exit."
    )
    cli_examples = [
        ("babel void --make-invite",  "host a room, print a void:// link"),
        ("babel void",                "open the lobby (paste a void:// link)"),
        ("babel void --setup",        "diagnostic (tor / mlock / xeddsa)"),
    ]
    threat_note = (
        "Blind relay -- the server never sees plaintext. SAS = 40 "
        "bits; verify it out-of-band. No PQ hybrid (HNDL risk)."
    )

    def status_line(self) -> str:
        # v1.0: no in-chrome chat state yet.  The status badge just
        # reflects 'idle / ready'.  When the chat client moves into
        # the chrome it will update this with peer count + latency.
        return "ready"


class MaskHomeView(ToolHomeView):
    name = "MASK"
    flavour = "ACTION"
    logo = art.MASK_LOGO
    summary = (
        "Disposable identity generator. Alias from a public-domain "
        "census-frequency catalog, deterministic geometric avatar, "
        "2-3 line bio, optional temp-mail handle over Tor."
    )
    cli_examples = [
        ("babel mask new",                       "generate a fresh identity"),
        ("babel mask new --locale es",           "Spanish-locale alias pool"),
        ("babel mask new --export ~/id.maskenc", "passphrase-encrypted bundle"),
        ("babel mask decode mask://...",         "parse a mask:// URL"),
    ]
    threat_note = (
        "Avatar is locally rendered (no reverse-image-search hit). "
        "Public temp-mail addresses are read by anyone."
    )


class StripHomeView(ToolHomeView):
    name = "STRIP"
    flavour = "ACTION"
    logo = art.STRIP_LOGO
    summary = (
        "Metadata laundry. Removes EXIF / XMP / IPTC from JPEG, "
        "text chunks from PNG, /Info + /Metadata from PDF, core / "
        "app / custom props from DOCX, ID3v2 / ID3v1 / APEv2 from "
        "MP3.  Byte-level parsers, no re-encode."
    )
    cli_examples = [
        ("babel strip ~/photo.jpg",            "strip in place"),
        ("babel strip -o out.png in.png",      "explicit output path"),
        ("babel strip --batch ~/photos/",      "walk a directory"),
        ("babel strip --aggressive doc.docx",  "drop rsids + trackChanges too"),
        ("babel strip --hash-rename file.pdf", "sha256-named output"),
    ]
    threat_note = (
        "Sensor noise, printer dots, and Office track-change residue "
        "in obscure XML survive. STRIP normalises; it does not guarantee 100%."
    )


class CarrierHomeView(ToolHomeView):
    name = "CARRIER"
    flavour = "ACTION"
    logo = art.CARRIER_LOGO
    summary = (
        "Steganography. AES-256-GCM payload + Argon2id KDF, hidden "
        "in the LSB plane of a PNG or WAV cover. No magic header "
        "in the output -- a plain cover and a wrong-passphrase "
        "attempt are indistinguishable."
    )
    cli_examples = [
        ("babel carrier embed cover.png secret.txt",  "embed into PNG"),
        ("babel carrier extract -o out.bin stego.png","recover the payload"),
        ("babel carrier capacity cover.wav",          "report safe payload size"),
        ("babel carrier inspect maybe-stego.png",     "chi-square sanity check"),
    ]
    threat_note = (
        "Lossy re-encoding destroys LSB payloads. A forensic analyst "
        "with the unmodified cover can detect tampering."
    )


class MirageHomeView(ToolHomeView):
    name = "MIRAGE"
    flavour = "SERVICE"
    logo = art.MIRAGE_LOGO
    summary = (
        "Cover-traffic generator. Real httpx requests over Tor "
        "SOCKS5h, Zipf-weighted per-profile site catalog, hard caps "
        "on bandwidth / request rate / CPU.  Configurable profiles: "
        "office_worker, developer, casual_browser, researcher."
    )
    cli_examples = [
        ("babel mirage start --profile office_worker", "background noise"),
        ("babel mirage start --honest",                "show each request as it fires"),
        ("babel mirage profiles",                      "list profile envelopes"),
        ("babel mirage --setup",                       "diagnostic"),
    ]
    threat_note = (
        "Bot-like patterns are still distinguishable under sophisticated "
        "analysis.  Running MIRAGE is itself a tell at the ISP level."
    )

    def status_line(self) -> str:
        # v1.0 home view does not drive the real engine; expose the
        # ceiling so the slot badge is informative.  When the engine
        # moves in-chrome this returns live rpm / kbpm.
        return "idle (use CLI to run)"


# ---------------------------------------------------------------------------
# Registry / lookup
# ---------------------------------------------------------------------------

_VIEW_CLASSES: dict[str, type[ToolHomeView]] = {
    "void":    VoidHomeView,
    "mask":    MaskHomeView,
    "strip":   StripHomeView,
    "carrier": CarrierHomeView,
    "mirage":  MirageHomeView,
}


def view_class_for(tool: str) -> type[ToolHomeView] | None:
    return _VIEW_CLASSES.get(tool.lower())


def all_tool_names() -> list[str]:
    return list(_VIEW_CLASSES.keys())


__all__ = [
    "ToolHomeView",
    "VoidHomeView",
    "MaskHomeView",
    "StripHomeView",
    "CarrierHomeView",
    "MirageHomeView",
    "view_class_for",
    "all_tool_names",
]
