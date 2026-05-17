"""STRIP diagnostic -- contributes to ``babel --setup``.

Per MASTER.md Section 6.3, every tool exports a ``run()`` returning
``(exit_code, list_of_lines)``. The aggregator concatenates them.
"""
from __future__ import annotations

from babel import theme


def run() -> tuple[int, list[str]]:
    g_ok = theme.glyph("active")
    g_warn = theme.glyph("warn")

    lines: list[str] = ["STRIP -- metadata laundry"]
    exit_code = 0

    # Native format support (stdlib only).
    for fmt in ("JPG/JPEG (stdlib)", "PNG (stdlib)",
                "DOCX (stdlib + xml.etree)", "MP3 (stdlib)"):
        lines.append(f"  {g_ok} {fmt}")

    # PDF requires pypdf.
    try:
        import pypdf  # noqa: F401
        version = getattr(pypdf, "__version__", "?")
        lines.append(f"  {g_ok} PDF (pypdf {version})")
    except ImportError:
        lines.append(f"  {g_warn} PDF disabled: install pypdf>=4.0")
        exit_code = 1

    return exit_code, lines


__all__ = ["run"]
