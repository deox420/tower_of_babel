"""Real progress bar -- bytes/s only, no decorative animation.

MASTER.md 3.2 forbids spinners that aren't tied to actual work.
``RealProgressBar`` updates only when its driver reports a new
``(done, total, rate)`` tuple, so the bar's motion *is* the work's
progress.

Pure-string renderer ``render_bar`` is the testable surface; the
Textual widget wraps it.
"""
from __future__ import annotations

from dataclasses import dataclass

from babel import theme


@dataclass(frozen=True, slots=True)
class ProgressState:
    done: int
    total: int
    rate_bps: float  # bytes per second, sampled by the caller


def _human_bytes(n: float) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while n >= 1024 and i < len(units) - 1:
        n /= 1024
        i += 1
    if i == 0:
        return f"{int(n)} {units[i]}"
    return f"{n:.2f} {units[i]}"


def render_bar(state: ProgressState, *, width: int = 40) -> str:
    """Render a progress bar string of total `width` columns.

    Layout::

        [######......] 42%  3.21 MB / 7.50 MB   1.4 MB/s

    No characters outside Tier-2 (MASTER.md 3.5) are emitted.
    """
    if width < 10:
        width = 10
    total = max(state.total, 1)
    done = max(0, min(state.done, state.total))
    pct = done / total
    fill = int(round(pct * width))

    bar_full = "#" * fill
    bar_empty = "." * (width - fill)
    pct_str = f"{pct * 100:5.1f}%"
    done_str = _human_bytes(done)
    total_str = _human_bytes(state.total)
    rate_str = f"{_human_bytes(state.rate_bps)}/s" if state.rate_bps > 0 else "-/s"
    return f"[{bar_full}{bar_empty}] {pct_str}  {done_str} / {total_str}   {rate_str}"


try:
    from textual.widgets import Static  # noqa: E402

    class RealProgressBar(Static):
        """Driver-fed progress bar widget.

        Call ``update_state(ProgressState(...))`` from your work loop
        (typically once per chunk written). The widget never advances
        on its own.
        """

        DEFAULT_CSS = f"""
        RealProgressBar {{
            color: {theme.CYAN};
            background: {theme.BG};
            width: 1fr;
            height: 1;
        }}
        """

        def __init__(self, *, width: int = 40, **kwargs) -> None:
            super().__init__("", **kwargs)
            self._bar_width = width
            self._state = ProgressState(0, 0, 0.0)

        def update_state(self, state: ProgressState) -> None:
            self._state = state
            self.update(render_bar(state, width=self._bar_width))

except ImportError:
    RealProgressBar = None  # type: ignore[assignment]


__all__ = ["ProgressState", "render_bar", "RealProgressBar"]
