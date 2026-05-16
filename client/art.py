LOGO = r"""
        ██╗   ██╗ ██████╗ ██╗██████╗
        ██║   ██║██╔═══██╗██║██╔══██╗
        ██║   ██║██║   ██║██║██║  ██║
        ╚██╗ ██╔╝██║   ██║██║██║  ██║
         ╚████╔╝ ╚██████╔╝██║██████╔╝
          ╚═══╝   ╚═════╝ ╚═╝╚═════╝
       //  e p h e m e r a l   n o d e  //
"""

SUB = "[ no logs · no disk · e2e · onion-only ]"

# Short boot sequence, shown frame-by-frame on cold start.
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

# Tiny scanline frame used as a decorative divider.
SCANLINE = "═" * 64

# "Mr. Robot"-flavoured one-liners shown at the bottom of the lobby.
HINTS = [
    "follow the rabbit_.",
    "control is an illusion.",
    "hello, friend.",
    "the world itself's just one big hoax.",
    "every revolution needs a quiet room.",
    "we are fsociety. we are silent.",
]
