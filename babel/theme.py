"""Tower of Babel palette + glyph vocabulary -- single source of truth.

These hex codes match the tokens in MASTER.md Section 3.3 character
for character. Every Textual ``.tcss`` and every inline
``style="..."`` string in the suite resolves back to one of the
seven names below. New tools must NOT introduce new colours; the
look is part of what makes the suite feel like one app.

The glyph vocabulary (MASTER.md 3.4) and the ASCII-fallback map
(MASTER.md 3.5) also live here because they are the same kind of
cross-tool constant: a fixed table the renderer reaches into.  The
chrome calls ``glyph(name)`` instead of hard-coding the Unicode
codepoint, so a single switch (``USE_ASCII_FALLBACK``) flips the
whole suite to Tier-1 ASCII output.
"""
from __future__ import annotations

import os
import shutil
import sys


# ---------------------------------------------------------------------------
# Palette (MASTER.md Section 3.3).
# ---------------------------------------------------------------------------
GREEN        = "#00ff9c"   # primary text, success, ready states
GREEN_DEEP   = "#003a25"   # inactive scanlines, dim borders
CYAN         = "#6cdcff"   # hints, secondary labels, selected items
AMBER        = "#ffd166"   # warnings, pending states, burn indicator
RED          = "#ff3860"   # errors, blocked actions, clearnet warning
MUTE         = "#7a7a7a"   # placeholders, separators, timestamps
BG           = "#000000"   # background everywhere


# ---------------------------------------------------------------------------
# Glyph table (MASTER.md 3.4) and ASCII fallback (MASTER.md 3.5).
# ---------------------------------------------------------------------------
# Keys are stable symbolic names; values are (tier-3 unicode, tier-1 ascii).
# Callers ask for ``glyph("active")``; the renderer picks the side based on
# ``use_ascii_fallback()``.
_GLYPH_TABLE: dict[str, tuple[str, str]] = {
    "active":     ("●", "*"),
    "off":        ("○", "."),
    "pending":    ("◐", "o"),
    "trusted":    ("✦", "+"),
    "warn":       ("⚠", "!"),
    "error":      ("✗", "x"),
    "rotating":   ("↻", "~"),
    "prompt":     ("▸", ">"),
    "sep":        ("·", "|"),
    "em":         ("—", "-"),
    # Box-drawing pairs used by the chrome border.
    "tl":         ("╔", "+"),
    "tr":         ("╗", "+"),
    "bl":         ("╚", "+"),
    "br":         ("╝", "+"),
    "vbar":       ("║", "|"),
    "hbar":       ("═", "-"),
    "ml":         ("╠", "+"),
    "mr":         ("╣", "+"),
    "hbar_light": ("─", "-"),
    "vbar_light": ("│", "|"),
}


# Forced override from environment / CLI. ``babel --setup`` sets this when
# its width-probe or $LANG / $TERM heuristic decides Tier-3 won't render.
USE_ASCII_FALLBACK: bool = False


def _env_says_ascii() -> bool:
    """Heuristic: does the environment look like a Tier-1-only terminal?"""
    if os.environ.get("BABEL_ASCII") == "1":
        return True
    lang = (os.environ.get("LANG") or "").lower()
    if lang == "c" or lang.startswith("c.") or lang.startswith("posix"):
        return True
    term = (os.environ.get("TERM") or "").lower()
    # Bare ``xterm`` without colour support is a strong signal we're on a
    # legacy box. ``xterm-256color`` is fine.
    if term in {"vt100", "vt220", "dumb", "linux"}:
        return True
    # If stdout can't encode our canonical Tier-3 glyph, fall back so the
    # CLI commands (--setup, batch summaries) don't UnicodeEncodeError on
    # Windows cp1252 / legacy locale consoles.
    enc = (getattr(sys.stdout, "encoding", None) or "").lower()
    if enc:
        try:
            "●".encode(enc)
        except (UnicodeEncodeError, LookupError):
            return True
    return False


def detect_ascii_fallback() -> bool:
    """Decide whether to render Tier-1 ASCII instead of Tier-3 glyphs.

    Called once at chrome mount.  Sets ``USE_ASCII_FALLBACK`` for the
    rest of the process.  ``--ascii`` on the CLI flips this on
    explicitly (see ``babel.__main__``).
    """
    global USE_ASCII_FALLBACK
    USE_ASCII_FALLBACK = _env_says_ascii()
    return USE_ASCII_FALLBACK


def use_ascii_fallback() -> bool:
    return USE_ASCII_FALLBACK


def force_ascii_fallback(on: bool) -> None:
    """Test hook + ``--ascii`` flag handler. Idempotent."""
    global USE_ASCII_FALLBACK
    USE_ASCII_FALLBACK = bool(on)


def glyph(name: str) -> str:
    """Return the glyph for ``name``, swapping in the ASCII fallback if set."""
    tier3, tier1 = _GLYPH_TABLE[name]
    return tier1 if USE_ASCII_FALLBACK else tier3


# ---------------------------------------------------------------------------
# Width probe -- compact mode kicks in below 80 cols (MASTER.md 3.5 #2).
# ---------------------------------------------------------------------------

COMPACT_THRESHOLD = 80
VERY_COMPACT_THRESHOLD = 60   # Termux portrait, default font


def terminal_width(default: int = 100) -> int:
    """Best-effort terminal width.  Never raises."""
    try:
        return shutil.get_terminal_size((default, 24)).columns
    except Exception:
        return default


def is_compact(width: int | None = None) -> bool:
    """True when the chrome should collapse labels (Termux landscape)."""
    w = width if width is not None else terminal_width()
    return w < COMPACT_THRESHOLD


def is_very_compact(width: int | None = None) -> bool:
    """True at the floor MASTER.md 3.5 commits to (60x20, Termux portrait).

    At this size we additionally drop the slot bar's per-service
    status text, use the narrow logo, and let menu rows wrap.
    """
    w = width if width is not None else terminal_width()
    return w < VERY_COMPACT_THRESHOLD


def width_tier(width: int | None = None) -> str:
    """Three-tier tag: 'narrow' (<60) / 'compact' (<80) / 'wide' (>=80)."""
    if is_very_compact(width):
        return "narrow"
    if is_compact(width):
        return "compact"
    return "wide"


__all__ = [
    "GREEN", "GREEN_DEEP", "CYAN", "AMBER", "RED", "MUTE", "BG",
    "glyph", "use_ascii_fallback", "force_ascii_fallback",
    "detect_ascii_fallback", "terminal_width",
    "is_compact", "is_very_compact", "width_tier",
    "COMPACT_THRESHOLD", "VERY_COMPACT_THRESHOLD",
]
