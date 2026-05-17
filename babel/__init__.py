"""Tower of Babel suite — launcher, shell, and shared TUI chrome.

The ``babel`` package owns the suite-wide multiplex shell (the
continuous outer frame, the status footer, the slot model from
MASTER.md Section 4.4) and the per-suite entry points. Individual
tools live under ``tools/`` and import from ``babel.*`` and
``shared.*`` only — never from each other.
"""
