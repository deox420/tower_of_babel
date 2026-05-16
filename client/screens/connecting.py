from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static


STEPS = [
    "reaching tor circuit",
    "connecting to .onion",
    "publishing identity bundle",
    "establishing ratchet sessions",
    "ready",
]


class ConnectingScreen(Screen):
    """Shown while VoidApp.enter_room walks through its setup phases.

    The app calls `set_step(idx)` to advance the indicator.
    """

    current = reactive(0)
    failed = reactive(False)
    failure_msg = reactive("")

    def __init__(self) -> None:
        super().__init__()
        self._spin_idx = 0

    def compose(self) -> ComposeResult:
        with Container(id="conn-container"):
            with Vertical(id="conn-card"):
                yield Static("// ESTABLISHING CHANNEL //", classes="title")
                yield Static(" ")
                yield Static(self._render_steps(), id="conn-steps")
                yield Static(" ")
                yield Static("press Ctrl+C to cancel", classes="sub")

    def on_mount(self) -> None:
        self._tick_timer = self.set_interval(0.15, self._spin)

    def _spin(self) -> None:
        self._spin_idx = (self._spin_idx + 1) % 4
        self.query_one("#conn-steps", Static).update(self._render_steps())

    def set_step(self, idx: int) -> None:
        self.current = idx
        try:
            self.query_one("#conn-steps", Static).update(self._render_steps())
        except Exception:
            pass

    def set_failed(self, msg: str) -> None:
        self.failed = True
        self.failure_msg = msg
        try:
            self.query_one("#conn-steps", Static).update(self._render_steps())
        except Exception:
            pass

    def _render_steps(self) -> Text:
        text = Text()
        spin = ".oOo"[self._spin_idx]
        for i, label in enumerate(STEPS):
            if self.failed and i == self.current:
                marker = "[!]"
                style = "bold #ff3860"
            elif i < self.current:
                marker = "[+]"
                style = "bold #00ff9c"
            elif i == self.current:
                marker = f"[{spin}]"
                style = "bold #6cdcff"
            else:
                marker = "[ ]"
                style = "dim #7a7a7a"
            text.append(f"  {marker}  {label}\n", style=style)
        if self.failed and self.failure_msg:
            text.append(f"\n  // {self.failure_msg}", style="bold #ff3860")
        return text
