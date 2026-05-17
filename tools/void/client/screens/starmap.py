from __future__ import annotations

import random

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Static


STAR_CHARS = ["·", "*", "✦", "✧", "°"]


class StarField(Widget):
    DEFAULT_CSS = """
    StarField {
        background: #000000;
        color: #00ff9c;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._uids: list[str] = []
        self._blink: dict[str, int] = {}

    def set_uids(self, uids: list[str]) -> None:
        self._uids = list(uids)
        self.refresh()

    def _coord_for(self, uid: str, w: int, h: int) -> tuple[int, int, str]:
        if len(uid) < 20 or w <= 2 or h <= 2:
            return 0, 0, STAR_CHARS[0]
        x = int(uid[0:8], 16) % (w - 2) + 1
        y = int(uid[8:16], 16) % (h - 2) + 1
        idx_a = int(uid[16:18], 16) % len(STAR_CHARS)
        idx_b = int(uid[18:20], 16) % len(STAR_CHARS)
        phase = self._blink.get(uid, 0)
        ch = STAR_CHARS[idx_a] if phase == 0 else STAR_CHARS[idx_b]
        return x, y, ch

    def on_mount(self) -> None:
        self.set_interval(0.1, self._tick)

    def _tick(self) -> None:
        if not self._uids:
            return
        rng = random.random
        # Slower blink on tiny terminals to reduce CPU on mobile.
        prob = 0.03 if getattr(self.app, "compact", False) else 0.07
        changed = False
        for uid in self._uids:
            if rng() < prob:
                self._blink[uid] = 1 - self._blink.get(uid, 0)
                changed = True
        if changed:
            self.refresh()

    def render(self) -> Text:
        w = max(self.size.width, 1)
        h = max(self.size.height, 1)
        grid = [[" "] * w for _ in range(h)]
        for uid in self._uids:
            x, y, ch = self._coord_for(uid, w, h)
            if 0 <= y < h and 0 <= x < w:
                grid[y][x] = ch
        out = Text()
        for r, row in enumerate(grid):
            out.append("".join(row), style="#00ff9c")
            if r < h - 1:
                out.append("\n")
        return out


class StarMapScreen(Screen):
    BINDINGS = [
        Binding("q", "back", "back", show=False),
        Binding("escape", "back", "back", show=False),
        Binding("ctrl+c", "app.purge_quit", "quit", priority=True, show=False),
        Binding("ctrl+q", "app.purge_quit", "quit", priority=True, show=False),
    ]

    count: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield StarField()
            yield Static("ACTIVE NODES: 0", id="starmap-footer")

    def update_users(self, uids: list[str]) -> None:
        self.query_one(StarField).set_uids(uids)
        self.query_one("#starmap-footer", Static).update(f"ACTIVE NODES: {len(uids)}    [q/esc] back")

    def action_back(self) -> None:
        self.app.pop_screen()
