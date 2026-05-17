"""Before/after diff table -- shared by STRIP and CARRIER.

Two surfaces:

* ``render_diff(rows, *, compact, max_width)`` -- pure string
  renderer the pentest harness can call without standing up
  Textual. Mirrors the ``render_footer`` pattern from the chrome.
* ``DiffTable`` -- Textual ``Static`` widget that wraps the same
  render function so the in-chrome view never diverges from what
  the tests see.

A row is a ``FieldRemoved`` named-tuple-shaped dict:

    {"field": "EXIF.GPSLatitude", "before": "41.385064", "after": "-"}

Real consumers can pass dataclass instances too; we duck-type on
the three keys above.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping

from babel import theme
from shared.ui.compact import fit, is_compact


@dataclass(frozen=True, slots=True)
class FieldRemoved:
    """One row of the diff. ``after`` is `'-'` for plain removal."""

    field: str
    before: str
    after: str = "-"


def _as_row(item: object) -> tuple[str, str, str]:
    if isinstance(item, FieldRemoved):
        return (item.field, item.before, item.after)
    if isinstance(item, Mapping):
        return (
            str(item.get("field", "")),
            str(item.get("before", "")),
            str(item.get("after", "-")),
        )
    raise TypeError(f"diff row must be FieldRemoved or Mapping, got {type(item)!r}")


def render_diff(
    rows: Iterable[object],
    *,
    compact: bool | None = None,
    max_width: int = 100,
) -> str:
    """Render the diff as a multi-line string.

    Wide form (>=80 cols): three columns separated by light vbars.
    Compact form (<80 cols): two columns (`field` + `before`); the
    `after` column is implicit (`-` for every row, which is what
    STRIP always emits).
    """
    rows_list = [_as_row(r) for r in rows]
    if compact is None:
        compact = is_compact(max_width)

    if not rows_list:
        return _empty_table(compact)

    hbar = theme.glyph("hbar_light")
    vbar = theme.glyph("vbar_light")

    if compact:
        field_w = min(28, max(len("field"), max(len(r[0]) for r in rows_list)))
        before_w = max_width - field_w - 5
        before_w = max(before_w, 10)

        lines: list[str] = []
        lines.append(f" {'field':<{field_w}} {vbar} {'before':<{before_w}}")
        lines.append(hbar * (field_w + before_w + 4))
        for f, b, _ in rows_list:
            lines.append(
                f" {fit(f, field_w):<{field_w}} {vbar} "
                f"{fit(b, before_w):<{before_w}}"
            )
        lines.append(hbar * (field_w + before_w + 4))
        lines.append(f" {len(rows_list)} fields removed.")
        return "\n".join(lines)

    field_w = min(30, max(len("field"), max(len(r[0]) for r in rows_list)))
    before_w = min(40, max(len("before"), max(len(r[1]) for r in rows_list)))
    after_w = min(20, max(len("after"), max(len(r[2]) for r in rows_list)))
    total = field_w + before_w + after_w + 7

    lines = []
    lines.append(
        f" {'field':<{field_w}} {vbar} {'before':<{before_w}} "
        f"{vbar} {'after':<{after_w}}"
    )
    lines.append(hbar * total)
    for f, b, a in rows_list:
        lines.append(
            f" {fit(f, field_w):<{field_w}} {vbar} "
            f"{fit(b, before_w):<{before_w}} {vbar} "
            f"{fit(a, after_w):<{after_w}}"
        )
    lines.append(hbar * total)
    lines.append(f" {len(rows_list)} fields removed.")
    return "\n".join(lines)


def _empty_table(compact: bool) -> str:
    hbar = theme.glyph("hbar_light")
    width = 40 if compact else 60
    return "\n".join([
        hbar * width,
        " no metadata found.",
        hbar * width,
    ])


try:
    from textual.widgets import Static  # noqa: E402

    class DiffTable(Static):
        """Textual widget wrapper around ``render_diff``.

        The widget owns no state beyond the row list it was
        constructed with; updates go through ``set_rows`` which
        re-renders the same string ``render_diff`` produces.
        """

        DEFAULT_CSS = f"""
        DiffTable {{
            color: {theme.GREEN};
            background: {theme.BG};
            width: 1fr;
            height: auto;
        }}
        """

        def __init__(self, rows: Iterable[object] = (),
                     *, max_width: int = 100, **kwargs) -> None:
            super().__init__("", **kwargs)
            self._rows = list(rows)
            self._max_width = max_width

        def on_mount(self) -> None:
            self._refresh()

        def set_rows(self, rows: Iterable[object]) -> None:
            self._rows = list(rows)
            self._refresh()

        def _refresh(self) -> None:
            self.update(render_diff(self._rows, max_width=self._max_width))

except ImportError:  # Textual missing -> CLI-only environment, fine.
    DiffTable = None  # type: ignore[assignment]


__all__ = ["FieldRemoved", "render_diff", "DiffTable"]
