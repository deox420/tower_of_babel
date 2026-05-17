"""Per-format byte-level metadata strippers.

Every public function takes ``data: bytes`` and an
``aggressive: bool`` keyword and returns ``StripResult``. None of
them touches the filesystem. None of them mutates ``data``.

Format dispatch (extension -> stripper) lives in
``tools.strip.pipeline``; the strippers here are independent.
"""
from __future__ import annotations

from tools.strip.core.jpeg import strip_jpeg
from tools.strip.core.png import strip_png
from tools.strip.core.pdf import strip_pdf
from tools.strip.core.docx import strip_docx
from tools.strip.core.mp3 import strip_mp3

__all__ = ["strip_jpeg", "strip_png", "strip_pdf", "strip_docx", "strip_mp3"]
