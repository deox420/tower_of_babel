"""Suite-wide ASCII art, tagline, and hint pool.

Three families live here, all pre-rendered (MASTER.md 3.5 forbids
computing logos at runtime):

* The **suite** assets -- ``BABEL_LOGO`` / ``BABEL_LOGO_NARROW`` /
  ``BABEL_TAGLINE`` / ``BABEL_HINTS`` -- own the chrome and the
  main menu.
* The **per-tool** assets -- ``VOID_LOGO`` / ``MASK_LOGO`` /
  ``STRIP_LOGO`` / ``CARRIER_LOGO`` / ``MIRAGE_LOGO`` -- one
  Tier-2 banner per tool, used by each tool's screen header.
* The **VOID legacy** assets -- ``LOGO`` / ``SUB`` / ``HINTS`` /
  ``BOOT_FRAMES`` / ``SCANLINE`` -- imported by
  ``tools/void/client/screens/lobby.py`` since Phase 0.  ``LOGO``
  is an alias of ``VOID_LOGO`` for backwards compatibility.

All multi-row constants below are uniform-width per row -- every
row in a logo has the same character count.  This is verified by
``pentest/babel/test_art_alignment.py`` so a misaligned glyph
never ships.

Character budget is Tier 2 (CP437 box-drawing + ASCII).  No Tier-3
glyphs leak into the logos themselves; the ASCII fallback layer in
``babel.theme`` handles Tier-3 substitutions when a terminal cannot
render them.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# Suite assets (Tower of Babel)
# ---------------------------------------------------------------------------

# Wide variant -- used at >=80 columns.  TOWER (44 cols) on top, BABEL
# (40 cols) centred two cols in below.  Every row inside each block is
# exactly the same width.  Pyfiglet "ANSI Shadow" output, verbatim.
BABEL_LOGO = (
    "████████╗ ██████╗ ██╗    ██╗███████╗██████╗ \n"
    "╚══██╔══╝██╔═══██╗██║    ██║██╔════╝██╔══██╗\n"
    "   ██║   ██║   ██║██║ █╗ ██║█████╗  ██████╔╝\n"
    "   ██║   ██║   ██║██║███╗██║██╔══╝  ██╔══██╗\n"
    "   ██║   ╚██████╔╝╚███╔███╔╝███████╗██║  ██║\n"
    "   ╚═╝    ╚═════╝  ╚══╝╚══╝ ╚══════╝╚═╝  ╚═╝\n"
    "                                            \n"
    "  ██████╗  █████╗ ██████╗ ███████╗██╗        \n"
    "  ██╔══██╗██╔══██╗██╔══██╗██╔════╝██║        \n"
    "  ██████╔╝███████║██████╔╝█████╗  ██║        \n"
    "  ██╔══██╗██╔══██║██╔══██╗██╔══╝  ██║        \n"
    "  ██████╔╝██║  ██║██████╔╝███████╗███████╗   \n"
    "  ╚═════╝ ╚═╝  ╚═╝╚═════╝ ╚══════╝╚══════╝   "
)

# Narrow variant -- used at <80 columns (Termux portrait at 60x20).
# One line of letterspacing, fits comfortably under the chrome at
# 60-col content width.
BABEL_LOGO_NARROW = "T O W E R   O F   B A B E L"

BABEL_TAGLINE = "confusion of tongues, by design"

# Mr.-Robot / VOID-flavoured one-liners; short, laconic, no exclamation
# marks (MASTER.md 3.7). Rotating in the main menu, never animated.
BABEL_HINTS = [
    "follow the rabbit_.",
    "the only winning move is not to play.",
    "trust the math, not the network.",
    "every door in this tower has a different lock.",
    "hello, friend.",
    "we are fsociety. we are silent.",
    "no logs. no disk. no excuses.",
    "control is an illusion.",
]


# ---------------------------------------------------------------------------
# Per-tool logos (each room in the tower)
# ---------------------------------------------------------------------------

# All in pyfiglet "ANSI Shadow", matching BABEL_LOGO.  Width per logo
# varies (the suite has no constraint on per-tool width), but every
# row WITHIN a logo is exactly the same character count.
# Tools render their own logo at the top of their primary screen.

VOID_LOGO = (
    "██╗   ██╗ ██████╗ ██╗██████╗ \n"
    "██║   ██║██╔═══██╗██║██╔══██╗\n"
    "██║   ██║██║   ██║██║██║  ██║\n"
    "╚██╗ ██╔╝██║   ██║██║██║  ██║\n"
    " ╚████╔╝ ╚██████╔╝██║██████╔╝\n"
    "  ╚═══╝   ╚═════╝ ╚═╝╚═════╝ "
)

MASK_LOGO = (
    "███╗   ███╗ █████╗ ███████╗██╗  ██╗\n"
    "████╗ ████║██╔══██╗██╔════╝██║ ██╔╝\n"
    "██╔████╔██║███████║███████╗█████╔╝ \n"
    "██║╚██╔╝██║██╔══██║╚════██║██╔═██╗ \n"
    "██║ ╚═╝ ██║██║  ██║███████║██║  ██╗\n"
    "╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝"
)

STRIP_LOGO = (
    "███████╗████████╗██████╗ ██╗██████╗ \n"
    "██╔════╝╚══██╔══╝██╔══██╗██║██╔══██╗\n"
    "███████╗   ██║   ██████╔╝██║██████╔╝\n"
    "╚════██║   ██║   ██╔══██╗██║██╔═══╝ \n"
    "███████║   ██║   ██║  ██║██║██║     \n"
    "╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝╚═╝     "
)

CARRIER_LOGO = (
    " ██████╗ █████╗ ██████╗ ██████╗ ██╗███████╗██████╗ \n"
    "██╔════╝██╔══██╗██╔══██╗██╔══██╗██║██╔════╝██╔══██╗\n"
    "██║     ███████║██████╔╝██████╔╝██║█████╗  ██████╔╝\n"
    "██║     ██╔══██║██╔══██╗██╔══██╗██║██╔══╝  ██╔══██╗\n"
    "╚██████╗██║  ██║██║  ██║██║  ██║██║███████╗██║  ██║\n"
    " ╚═════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝╚══════╝╚═╝  ╚═╝"
)

MIRAGE_LOGO = (
    "███╗   ███╗██╗██████╗  █████╗  ██████╗ ███████╗\n"
    "████╗ ████║██║██╔══██╗██╔══██╗██╔════╝ ██╔════╝\n"
    "██╔████╔██║██║██████╔╝███████║██║  ███╗█████╗  \n"
    "██║╚██╔╝██║██║██╔══██╗██╔══██║██║   ██║██╔══╝  \n"
    "██║ ╚═╝ ██║██║██║  ██║██║  ██║╚██████╔╝███████╗\n"
    "╚═╝     ╚═╝╚═╝╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝ ╚══════╝"
)

# Per-tool one-line subtitles -- displayed under each tool's logo.
TOOL_TAGLINES = {
    "void":    "ephemeral encrypted messenger",
    "mask":    "disposable identity generator",
    "strip":   "metadata laundry",
    "carrier": "steganography (PNG / WAV)",
    "mirage":  "cover traffic generator",
}


# ---------------------------------------------------------------------------
# VOID legacy assets (Phase-0 carry-over -- consumed by
# tools/void/client/screens/lobby.py)
# ---------------------------------------------------------------------------

# LOGO is the VOID lobby banner: the VOID block art followed by the
# legacy "ephemeral node" tagline line.  The lobby Static renders it
# with text-align: center, so per-row width does not need to match.
LOGO = VOID_LOGO + "\n//  e p h e m e r a l   n o d e  //"

SUB = "[ no logs * no disk * e2e * onion-only ]"

BOOT_FRAMES = [
    "  > initializing void.kernel",
    "  > initializing void.kernel  [....]",
    "  > initializing void.kernel  [OK]",
    "  > probing tor circuit       [....]",
    "  > probing tor circuit       [OK]",
    "  > locking memory pages      [....]",
    "  > locking memory pages      [OK]",
    "  > you are now invisible.",
]

SCANLINE = "═" * 64

# Kept for backwards compat with VOID's lobby.  New code should import
# ``BABEL_HINTS`` from this module instead.
HINTS = [
    "follow the rabbit_.",
    "control is an illusion.",
    "hello, friend.",
    "the world itself's just one big hoax.",
    "every revolution needs a quiet room.",
    "we are fsociety. we are silent.",
]
