"""Diff plumbing -- per-format strippers all return ``StripResult``.

The ``removed`` field is a flat list of ``shared.ui.diff_view.FieldRemoved``
rows so the same widget renders STRIP's output in the chrome and
the CLI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from shared.ui.diff_view import FieldRemoved


@dataclass(slots=True)
class StripResult:
    """Returned by every ``strip_<format>(data, *, aggressive)`` function."""

    payload: bytes
    removed: list[FieldRemoved] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.removed)


__all__ = ["StripResult", "FieldRemoved"]
