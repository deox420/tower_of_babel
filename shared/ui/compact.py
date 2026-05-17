"""Width-based label adapters (MASTER.md 3.5 layout rule #2).

Compact mode kicks in below ``theme.COMPACT_THRESHOLD`` (80 cols).
Glyphs from ``theme.glyph`` stay the same; labels collapse. This
module owns the rule so every consumer collapses identically.
"""
from __future__ import annotations

from babel import theme


def is_compact(width: int | None = None) -> bool:
    return theme.is_compact(width)


def short_label(wide: str, compact: str | None = None,
                width: int | None = None) -> str:
    """Pick the wide or compact form for a label.

    If ``compact`` is omitted, the compact form is the first letter
    of ``wide`` (matching the footer's `T M C S` convention).
    """
    if not is_compact(width):
        return wide
    if compact is None:
        return wide[:1] if wide else wide
    return compact


def fit(text: str, width: int, ellipsis: str = "...") -> str:
    """Truncate ``text`` to ``width`` columns, appending ``ellipsis``.

    Width is measured in code points, not display width. That is
    intentional: the suite's character tiers (MASTER.md 3.5) keep
    every visible character single-cell, and the renderer rejects
    anything wider before it reaches here.
    """
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= len(ellipsis):
        return text[:width]
    return text[: width - len(ellipsis)] + ellipsis


__all__ = ["is_compact", "short_label", "fit"]
