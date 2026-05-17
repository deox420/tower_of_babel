"""Step indicator -- visual progress for multi-phase actions.

Inspired by VOID's ``ConnectingScreen`` step block (MASTER.md
Section 5.5). Used by tools that run a handful of named phases
where each phase is a real, blocking unit of work: MASK (alias ->
avatar -> mail -> bundle), CARRIER's future "embed and verify"
preview, and any future tool that does the same.

Two surfaces:

- ``render_steps()`` is a pure-string renderer the CLI and the
  pentest harness call directly.
- ``StepIndicator`` is a thin Textual widget wrapping the renderer.

Glyphs go through ``babel.theme.glyph()`` so the suite-wide ASCII
fallback (MASTER.md Section 3.5) flips this widget too.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal, Sequence

from babel import theme


StepState = Literal["pending", "active", "done", "failed"]


@dataclass(frozen=True)
class Step:
    """One phase. ``label`` is short (single line). ``state`` cycles
    through ``pending`` -> ``active`` -> ``done`` (or ``failed``)."""

    label: str
    state: StepState = "pending"
    detail: str = ""    # optional short trailer, e.g. "via mail.tm"


def _glyph_for(state: StepState) -> str:
    if state == "active":
        return theme.glyph("pending")    # ◐ / o
    if state == "done":
        return theme.glyph("active")     # ● / *
    if state == "failed":
        return theme.glyph("error")      # ✗ / x
    return theme.glyph("off")            # ○ / .


def render_steps(steps: Sequence[Step]) -> str:
    """Render the step block as a single string with one line per step.

    Format: ``"  <glyph>  <label>[  detail]"``. Two leading spaces
    so the block visually indents under a section header.
    """
    lines: list[str] = []
    for step in steps:
        g = _glyph_for(step.state)
        trailer = f"  {step.detail}" if step.detail else ""
        lines.append(f"  {g}  {step.label}{trailer}")
    return "\n".join(lines)


def advance(steps: Sequence[Step], index: int,
            *, state: StepState, detail: str | None = None) -> list[Step]:
    """Return a copy of ``steps`` with ``steps[index]`` updated.

    Convenience for callers that hold a tuple of Steps and want a
    new list back without mutating the original. ``detail=None``
    leaves the existing detail intact; pass ``detail=""`` to clear.
    """
    if index < 0 or index >= len(steps):
        raise IndexError(f"step index {index} out of range {len(steps)}")
    out = list(steps)
    new_detail = out[index].detail if detail is None else detail
    out[index] = replace(out[index], state=state, detail=new_detail)
    return out


# Lazy textual import so the pure renderer works in headless tests.
def _StepIndicator():    # noqa: N802 -- this is a factory, not a class
    from textual.widgets import Static

    class StepIndicator(Static):    # type: ignore[misc]
        """Textual widget wrapper around ``render_steps``."""

        DEFAULT_CSS = f"""
        StepIndicator {{
            color: {theme.GREEN};
            background: {theme.BG};
            padding: 0 1;
        }}
        """

        def __init__(self, steps: Sequence[Step] = (), **kwargs) -> None:
            super().__init__(render_steps(steps), **kwargs)
            self._steps: list[Step] = list(steps)

        def set_steps(self, steps: Sequence[Step]) -> None:
            self._steps = list(steps)
            self.update(render_steps(self._steps))

        def advance(self, index: int, *, state: StepState,
                    detail: str | None = None) -> None:
            self._steps = advance(self._steps, index,
                                  state=state, detail=detail)
            self.update(render_steps(self._steps))

        @property
        def steps(self) -> list[Step]:
            return list(self._steps)

    return StepIndicator


def __getattr__(name: str):
    """Lazy attribute access so importing this module does not require
    Textual at import time (the pure renderer is the headless surface)."""
    if name == "StepIndicator":
        return _StepIndicator()
    raise AttributeError(name)


__all__ = ["Step", "StepState", "render_steps", "advance", "StepIndicator"]
