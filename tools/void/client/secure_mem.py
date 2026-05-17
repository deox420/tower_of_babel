"""Compatibility shim: secure_mem now lives in shared/crypto/.

Phase 0 extracted the canonical implementation to
``shared.crypto.secure_mem`` so other tools (MASK, CARRIER) can use
it without depending on VOID. The names ``SecureBytes``,
``mlock_status``, ``swap_active``, ``MLOCK_OK``, ``MLOCK_REASON``
remain importable here so existing call sites
(``tools.void.client.setup_check``,
``tools.void.client.screens.lobby``, the pentest suite) keep
working without edit. Future phases should migrate consumers to
import directly from ``shared.crypto.secure_mem`` and drop this
shim.
"""
from __future__ import annotations

from shared.crypto.secure_mem import *  # noqa: F401, F403
