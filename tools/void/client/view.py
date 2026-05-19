"""VOID's in-chrome surface.

Phase 7 introduces the chrome-mounted ``VoidView``: a lobby-shaped
container that the babel chrome's menu mounts when the user picks
[1] VOID.  The view exposes the Service Protocol via a separate
``_VoidBoundService`` object (decision-log entry 2026-05-19) so
the registry can hold the Service without dragging Textual into
pentest.

Phase-7 scope note (known deviation, see CHANGELOG.md):
The chat + connecting + starmap flows still live in ``client/app.py``
as Textual ``Screen`` subclasses.  ``VoidView.start_session`` does
NOT run them in-chrome yet -- it exits the chrome with a structured
return value that ``babel.__main__`` consumes to relaunch the full
``VoidApp`` against the populated lobby args.  The chrome stays
responsible for the *menu* and the *lobby*; chat itself still owns
the terminal until /leave or /burn.  Subsequent post-1.0 work
(tracked in RELEASE_NOTES "Known deviations") replaces the bridge
with native push_view of LobbyView / ConnectingView / ChatView /
StarmapView.
"""
from __future__ import annotations

from typing import Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Button, Input, Static

from babel import theme
from babel.art import BABEL_TAGLINE
from shared.crypto.secure_mem import mlock_status

from .link import decode as decode_invite


def _is_ascii_printable(s: str) -> bool:
    return 1 <= len(s) <= 64 and all(0x20 <= ord(c) <= 0x7E for c in s)


def _strip_url_prefix(s: str) -> str:
    for pfx in ("ws://", "wss://", "http://", "https://"):
        if s.startswith(pfx):
            return s[len(pfx):]
    return s


class _VoidBoundService:
    """Service-protocol adapter bound to a ``VoidView``.

    Lobby surfaces have no session state, so the contributions are
    minimal: the slot bar shows "lobby" until session start hands
    off to the legacy chat flow.  ``purge_local`` zeros the
    passphrase / room key inputs the view holds so a Ctrl+W tears
    down the secrets even when the user never reached the chat.
    """

    name = "VOID"

    def __init__(self, view: "VoidView") -> None:
        self.view = view
        self._purged = False

    def status_line(self) -> str:
        if self._purged:
            return "(purged)"
        if self.view._session_pending:
            return "joining..."
        return "lobby"

    def footer_contribution(self) -> dict[str, str]:
        # The lobby itself does not hold key material -- chat does,
        # and chat runs out-of-chrome today.  CRYPTO stays dim.
        return {}

    async def purge_local(self) -> None:
        if self._purged:
            return
        try:
            self.view._zero_inputs()
        except Exception:
            pass
        self._purged = True

    def resource_caps(self) -> dict[str, float]:
        return {}


class VoidView(Container):
    """Ephemeral encrypted messenger -- lobby pasteboard.

    Service-flavoured.  Mounted inside the babel chrome's content
    slot when the user picks [1] from the menu (MASTER.md 4.4,
    docs/NAVIGATION.md section 4).  Holds an invite / server / room
    / password set of inputs that mirror the legacy LobbyScreen.
    Pressing ENTER hands off to the chrome which runs the actual
    session (see module docstring for the v1.0 bridge note).
    """

    name = "VOID"
    flavour = "SERVICE"
    can_focus = True

    DEFAULT_CSS = f"""
    VoidView {{
        background: {theme.BG};
        color: {theme.GREEN};
        height: 1fr;
        width: 1fr;
        padding: 1 2;
    }}
    VoidView .title  {{ color: {theme.GREEN}; text-style: bold; }}
    VoidView .tagline {{ color: {theme.CYAN}; text-style: dim italic; }}
    VoidView .hint    {{ color: {theme.CYAN}; text-style: dim; }}
    VoidView .label   {{ color: {theme.MUTE}; }}
    VoidView .err     {{ color: {theme.RED};  text-style: bold; }}
    VoidView .ok      {{ color: {theme.GREEN}; }}
    VoidView Input {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    VoidView Button {{
        background: {theme.BG};
        color: {theme.GREEN};
        border: tall {theme.GREEN_DEEP};
    }}
    """

    BINDINGS = [
        Binding("escape", "leave",  "back to menu", show=True, priority=True),
        Binding("alt+0",  "leave",  "menu",         show=False, priority=True),
        Binding("ctrl+w", "leave",  "close slot",   show=False, priority=True),
    ]

    def __init__(self, default_server: str = "") -> None:
        super().__init__()
        self._default_server = default_server
        self._session_pending = False
        self._err: Static | None = None
        self._invite: Input | None = None
        self._server: Input | None = None
        self._room:   Input | None = None
        self._pw:     Input | None = None
        # Service exposed to the registry.
        self.service = _VoidBoundService(self)

    def compose(self) -> ComposeResult:
        st = mlock_status()
        with Vertical():
            yield Static("VOID -- ephemeral encrypted messenger",
                         classes="title")
            yield Static(BABEL_TAGLINE, classes="tagline")
            yield Static(" ")
            yield Static(self._mem_line(st), classes="label")
            yield Static(" ")
            yield Static("PASTE AN INVITE  (void://...)", classes="label")
            self._invite = Input(placeholder="void://...", id="void-invite",
                                 max_length=2048)
            yield self._invite
            yield Static("  -- or --", classes="hint")
            yield Static(".onion ADDRESS", classes="label")
            self._server = Input(placeholder="xxxxx.onion:8765",
                                 id="void-server",
                                 value=self._default_server, max_length=120)
            yield self._server
            yield Static("ROOM KEY", classes="label")
            self._room = Input(placeholder="short shared name",
                               id="void-room", max_length=64)
            yield self._room
            yield Static("PASSWORD", classes="label")
            self._pw = Input(placeholder="short shared secret",
                             id="void-pw", password=True, max_length=64)
            yield self._pw
            yield Static(" ")
            yield Button("ENTER", id="void-enter", variant="success")
            self._err = Static("", id="void-err", classes="hint")
            yield self._err

    # ----- mlock notice ----------------------------------------------------

    def _mem_line(self, st: dict) -> str:
        if st.get("swap_active") and not st.get("mlock_ok"):
            return "swap active, mlock unavailable -- prefix room key with '!ack-' to override"
        if st.get("mlock_ok"):
            return "mlock: ok"
        return "mlock: unavailable (swap inactive -- lower risk)"

    # ----- lobby UX --------------------------------------------------------

    def on_mount(self) -> None:
        try:
            self.focus()
            if self._invite is not None:
                self._invite.focus()
        except Exception:
            pass

    async def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "void-invite":
            return
        val = event.value.strip()
        if not val:
            return
        inv = decode_invite(val)
        if inv is None:
            return
        if self._server is not None:
            self._server.value = inv.onion
        if self._room is not None:
            self._room.value = inv.room
        if self._pw is not None:
            self._pw.value = inv.password
        self._set_err("invite accepted. press ENTER to join.", "ok")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "void-enter":
            await self._try_enter()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        await self._try_enter()

    async def _try_enter(self) -> None:
        if self._room is None or self._pw is None or self._server is None:
            return
        room = self._room.value
        pw = self._pw.value
        server_in = self._server.value.strip()
        if not _is_ascii_printable(room):
            self._set_err("room key must be 1-64 printable characters", "err")
            return
        if not _is_ascii_printable(pw):
            self._set_err("password must be 1-64 printable characters", "err")
            return
        host = _strip_url_prefix(server_in)
        if not host or ".onion" not in host:
            self._set_err("address must end in .onion (e.g. xxxxx.onion:8765)",
                          "err")
            return
        if ":" not in host:
            host = host + ":8765"

        # Phase 7 v1.0 bridge: hand the lobby args back to babel.__main__
        # to relaunch the legacy VoidApp.  Subsequent post-1.0 work
        # replaces this with a native in-chrome handshake.
        self._session_pending = True
        self._set_err("joining (handing off to chat...)", "ok")

        bridge = getattr(self.app, "void_session_bridge", None)
        if callable(bridge):
            bridge({
                "room":     room,
                "password": pw,
                "server":   f"ws://{host}",
                "onion":    host,
            })
        else:
            # No chrome bridge wired (e.g. running under the bare
            # legacy VoidApp); leave the user in the lobby.
            self._set_err("no session bridge attached", "err")
            self._session_pending = False

    # ----- paste-routing entry (docs/NAVIGATION.md section 6) --------------

    def prefill_invite(self, url: str) -> None:
        """Fill the invite field from a ``void://`` URL pasted in the menu.

        The lobby's existing ``on_input_changed`` handler then
        autofills the three sub-fields and announces "invite
        accepted".
        """
        if self._invite is not None:
            self._invite.value = url
            try:
                self._invite.focus()
            except Exception:
                pass

    # ----- helpers ---------------------------------------------------------

    def _set_err(self, text: str, cls: str) -> None:
        if self._err is None:
            return
        self._err.update(text)
        self._err.set_classes(f"hint {cls}".strip() if cls else "hint")

    def _zero_inputs(self) -> None:
        """Wipe the secrets the user typed into the lobby.

        Called by the Service's ``purge_local`` on Ctrl+W / Ctrl+C.
        Best-effort: Textual Inputs hold their value as a Python
        ``str`` which we cannot truly zero, but we overwrite the
        attribute with an empty string so the GC can drop it on
        the next collection.
        """
        for inp in (self._invite, self._server, self._room, self._pw):
            if inp is None:
                continue
            try:
                inp.value = ""
            except Exception:
                pass

    # ----- chrome action handler -------------------------------------------

    def action_leave(self) -> None:
        leave = getattr(self.app, "leave_tool", None)
        if callable(leave):
            leave(self)


__all__ = ["VoidView", "_VoidBoundService"]
