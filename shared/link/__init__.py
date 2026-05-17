"""Multi-scheme invite codec (MASTER.md Section 5.6).

A single source of truth for the suite's ``void://`` / ``carrier://``
/ ``mask://`` URL forms. Each tool has its own paste-autofill flow
in the lobby; ``looks_like()`` and ``decode()`` are the gateway.
"""
from __future__ import annotations
