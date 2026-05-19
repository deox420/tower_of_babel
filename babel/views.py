"""In-chrome tool view registry.

Phase 7 (MASTER.md 4.4, docs/NAVIGATION.md):
The chrome mounts the live tool surface itself -- no info-only
stub views between the menu and the real tool.  The Phase 1
``ToolHomeView`` dataclass is gone; ``view_class_for(name)``
returns the per-tool ``*View`` class from ``tools/<name>/app.py``
(or ``tools/void/client/view.py`` for VOID).

Each per-tool view declares two class attrs:

* ``name``    -- short uppercase tag (matches the menu).
* ``flavour`` -- ``"SERVICE"`` or ``"ACTION"`` (MASTER.md 4.4).

SERVICE-flavoured views additionally expose ``self.service``,
the ``Service`` protocol implementation that goes into the
chrome's ``ServiceRegistry``.  The Service is a *separate* object
owned by the view (2026-05-19 decision-log entry in
docs/ARCHITECTURE.md): it survives the view being unmounted, and
pentest tests can drive its protocol without importing Textual.

Imports are lazy.  Importing ``babel.views`` does not import
Textual; each tool's heavy imports (httpx for MIRAGE, cryptography
for CARRIER, etc.) only kick in when the user actually picks the
tool from the menu.
"""
from __future__ import annotations

from typing import Callable


# ---------------------------------------------------------------------------
# Lazy loaders.  Each returns the View class for one tool.
# ---------------------------------------------------------------------------


def _void():
    from tools.void.client.view import VoidView
    return VoidView


def _mask():
    from tools.mask.app import MaskView
    return MaskView


def _strip():
    from tools.strip.app import StripView
    return StripView


def _carrier():
    from tools.carrier.app import CarrierView
    return CarrierView


def _mirage():
    from tools.mirage.app import MirageView
    return MirageView


_LOADERS: dict[str, Callable[[], type]] = {
    "void":    _void,
    "mask":    _mask,
    "strip":   _strip,
    "carrier": _carrier,
    "mirage":  _mirage,
}


# Static metadata: declared up-front so the chrome can render the
# menu and the slot bar without forcing every tool's heavy imports
# to load just to ask "what's your flavour?".
_TOOL_META: dict[str, dict[str, str]] = {
    "void":    {"name": "VOID",    "flavour": "SERVICE"},
    "mask":    {"name": "MASK",    "flavour": "ACTION"},
    "strip":   {"name": "STRIP",   "flavour": "ACTION"},
    "carrier": {"name": "CARRIER", "flavour": "ACTION"},
    "mirage":  {"name": "MIRAGE",  "flavour": "SERVICE"},
}


def view_class_for(tool: str) -> type | None:
    """Return the View class for ``tool``, lazy-importing on demand."""
    loader = _LOADERS.get(tool.lower())
    return loader() if loader is not None else None


def all_tool_names() -> list[str]:
    return list(_LOADERS.keys())


def tool_meta(tool: str) -> dict[str, str] | None:
    """Return ``{'name': 'VOID', 'flavour': 'SERVICE'}`` for ``tool``.

    Does not import anything; reads the static table above.  Used
    by the menu to decide whether to render "(live in slot N)" next
    to a tool entry, without triggering the per-tool import chain.
    """
    return _TOOL_META.get(tool.lower())


def tool_meta_all() -> dict[str, dict[str, str]]:
    """Snapshot of the meta table (defensive copy)."""
    return {k: dict(v) for k, v in _TOOL_META.items()}


__all__ = [
    "view_class_for", "all_tool_names",
    "tool_meta", "tool_meta_all",
]
