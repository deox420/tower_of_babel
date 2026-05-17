"""Hex dump view -- shared by CARRIER (payload preview) and future tools.

Pure-string renderer + thin Textual widget, same pattern as
``diff_view`` and ``progress``. The renderer is the testable
surface; the widget wraps it.

Output shape (16 bytes per row, default)::

    00000000  42 30 42 4c 01 8f 3c 2a  9d 21 7e 80 0a 0a 0a 0a  |B0BL..<*.!~.....|
    00000010  ff 00 ff 00 ff 00 ff 00  ff 00 ff 00 ff 00 ff 00  |................|
"""
from __future__ import annotations

from babel import theme


_PRINTABLE = bytes(range(0x20, 0x7f))  # space..~


def render_hex(data: bytes, *, width: int = 16, offset: int = 0,
               max_rows: int | None = None) -> str:
    """Render ``data`` as a hex dump.

    Parameters
    ----------
    width
        bytes per row (default 16). Smaller widths suit compact terminals.
    offset
        starting offset for the address column.
    max_rows
        truncate after this many rows; ``None`` for no limit. When
        truncated, the last line is ``... (<n> more bytes)``.
    """
    if width < 4:
        width = 4

    if not data:
        return "(empty)"

    lines: list[str] = []
    n_rows = (len(data) + width - 1) // width
    rows_to_render = n_rows if max_rows is None else min(n_rows, max_rows)

    for r in range(rows_to_render):
        start = r * width
        chunk = data[start:start + width]
        lines.append(_format_row(chunk, offset + start, width))

    if max_rows is not None and n_rows > max_rows:
        rest = len(data) - rows_to_render * width
        lines.append(f"... ({rest} more bytes)")

    return "\n".join(lines)


def _format_row(chunk: bytes, addr: int, width: int) -> str:
    half = width // 2
    hex_left = " ".join(f"{b:02x}" for b in chunk[:half])
    hex_right = " ".join(f"{b:02x}" for b in chunk[half:])
    # Pad short final row so the ASCII column aligns.
    hex_left = hex_left.ljust(half * 3 - 1)
    hex_right = hex_right.ljust(half * 3 - 1)
    ascii_part = "".join(
        chr(b) if b in _PRINTABLE else "." for b in chunk
    )
    return f"{addr:08x}  {hex_left}  {hex_right}  |{ascii_part}|"


try:
    from textual.widgets import Static  # noqa: E402

    class HexView(Static):
        """Textual widget wrapper around ``render_hex``."""

        DEFAULT_CSS = f"""
        HexView {{
            color: {theme.GREEN};
            background: {theme.BG};
            width: 1fr;
            height: auto;
        }}
        """

        def __init__(self, data: bytes = b"", *, width: int = 16,
                     max_rows: int | None = None, **kwargs) -> None:
            super().__init__("", **kwargs)
            self._data = data
            self._width = width
            self._max_rows = max_rows

        def on_mount(self) -> None:
            self._refresh()

        def set_data(self, data: bytes, *, offset: int = 0) -> None:
            self._data = data
            self._offset = offset
            self._refresh()

        def _refresh(self) -> None:
            self.update(render_hex(
                self._data, width=self._width, max_rows=self._max_rows,
            ))

except ImportError:
    HexView = None  # type: ignore[assignment]


__all__ = ["render_hex", "HexView"]
