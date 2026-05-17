"""Reusable TUI primitives consumed across tools (MASTER.md 5.5).

These modules host widgets and pure-string renderers that more than
one tool needs: the box-drawn before/after diff (STRIP, CARRIER),
the real-progress bar (STRIP, CARRIER, MIRAGE), and the compact-mode
label adapters. The pure-string variant of each renderer is what
``pentest/`` consumes, mirroring the pattern set by
``babel.shell.render_footer``.
"""
