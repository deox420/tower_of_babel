from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static


PANEL_1 = """\
WHAT IS VOID?

A terminal chat that disappears.

  • No accounts. No history. No phone numbers.
  • Everything you type is encrypted end-to-end on your machine.
  • The server can never read it. Neither can the network.
  • When you close the program, it's gone. As if it never happened.

To talk to someone, you both need:
  1. An INVITE link  (or three fields: address, room key, password).
  2. The Tor service running on your computer.
"""

PANEL_2 = """\
HOW DO I JOIN — OR HOST?

JOIN (the easy way):
  • Someone sends you a 'void://...' link by a trusted channel.
  • Paste it into the INVITE field in the lobby. Press ENTER.

JOIN (manual, no link):
  • Get the .onion address, the room key, and the password from
    your peer. Type each into its field. Press ENTER.

HOST (one command, no torrc surgery):
  • Make sure Tor is running with its control port open.
  • In a terminal:   void --make-invite
  • You get a 'void://...' link. Send it to your peer.
  • Keep that terminal open — when you Ctrl+C, the onion dies.

If anything fails, you'll see a plain-English message saying why.
"""

PANEL_3 = """\
IS IT ACTUALLY PRIVATE?

VOID protects what you SAY.
VOID cannot protect against:

  • Someone looking over your shoulder.
  • Screenshots your peer takes of the chat.
  • A virus on your computer.
  • You sharing the invite with the wrong person.

To make sure you're really talking to who you think you are:
  Type '/verify' followed by your peer's 4-letter ID
  (you'll see it next to their messages).
  The app shows 5 words. Read them out loud.
  If your peer hears the same 5 words, it's really them.

Press ESC to go back. Press 'q' to quit help.
"""


class WelcomeScreen(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "back", show=False),
        Binding("q", "dismiss", "back", show=False),
        Binding("right", "next_panel", "next", show=False),
        Binding("left", "prev_panel", "prev", show=False),
        Binding("enter", "next_panel", "next", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._panels = [PANEL_1, PANEL_2, PANEL_3]
        self._idx = 0

    def compose(self) -> ComposeResult:
        with Container(id="welcome-container"):
            with Vertical(id="welcome-card"):
                yield Static("// FIRST TIME? READ THIS //", classes="title")
                yield Static(self._panels[self._idx], id="welcome-text")
                yield Static(self._nav_text(), id="welcome-nav", classes="sub")

    def _nav_text(self) -> str:
        return f"  [{self._idx + 1}/{len(self._panels)}]   ← prev  →/Enter next   Esc close"

    def action_next_panel(self) -> None:
        if self._idx < len(self._panels) - 1:
            self._idx += 1
            self.query_one("#welcome-text", Static).update(self._panels[self._idx])
            self.query_one("#welcome-nav", Static).update(self._nav_text())
        else:
            self.dismiss()

    def action_prev_panel(self) -> None:
        if self._idx > 0:
            self._idx -= 1
            self.query_one("#welcome-text", Static).update(self._panels[self._idx])
            self.query_one("#welcome-nav", Static).update(self._nav_text())

    def action_dismiss(self) -> None:
        self.dismiss()
