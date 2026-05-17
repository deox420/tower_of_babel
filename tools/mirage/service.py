"""``MirageService`` -- the chrome-resident wrapper around ``MirageEngine``.

Implements the ``babel.shell.Service`` Protocol so a running MIRAGE
can sit in slot 2 of the chrome while VOID owns the foreground.

The Service is created by ``tools.mirage.app.MirageView`` when the
user presses ``[s]`` in the screen.  It is destroyed by
``purge_local()``, which the chrome calls on Ctrl+W (close slot)
or on Ctrl+C / Ctrl+Q (quit suite).
"""
from __future__ import annotations

import asyncio
from typing import Optional

from tools.mirage.engine import EngineConfig, Event, MirageEngine, Transport


class MirageService:
    """Service-Protocol shim around the engine.

    The chrome only ever sees the four methods the protocol asks for
    (``status_line``, ``footer_contribution``, ``purge_local``,
    ``resource_caps``).  Everything else is for the foreground view.
    """

    name = "MIRAGE"

    def __init__(
        self,
        engine: MirageEngine,
        view=None,                # optional Textual widget for Alt+N to jump back to
    ) -> None:
        self.engine = engine
        self.view = view          # chrome reads this for Alt+<digit> jump
        self._purged = False

    # ----- Service protocol -------------------------------------------------

    def status_line(self) -> str:
        snap = self.engine.snapshot()
        reqs = snap.get("requests", 0)
        bytes_in = int(snap.get("bytes_in", 0))
        # KB/min average over uptime (round to int for the chrome).
        up = max(1.0, float(snap.get("uptime_sec", 1.0)))
        kbpm = int((bytes_in / 1024.0) / (up / 60.0))
        rpm = int(reqs / max(1.0, up / 60.0))
        if snap.get("paused"):
            return f"paused {reqs} reqs"
        return f"{rpm} rpm {kbpm} KB/min"

    def footer_contribution(self) -> dict[str, str]:
        # MIRAGE participates in the TOR indicator when use_tor is on AND
        # the engine is actually running.  It never holds key material
        # (no CRYPTO contribution) and never mlocks (no MEM contribution).
        contrib: dict[str, str] = {}
        if self.engine.is_running() and self.engine.config.use_tor:
            contrib["TOR"] = "on"
        return contrib

    async def purge_local(self) -> None:
        if self._purged:
            return
        try:
            await asyncio.wait_for(self.engine.stop(), timeout=0.95)
        except (asyncio.TimeoutError, Exception):
            pass
        self._purged = True

    def resource_caps(self) -> dict[str, float]:
        cfg = self.engine.config
        return {
            "bandwidth_kbps": float(cfg.bw_kbps),
            "rate_rpm":       float(cfg.rate_rpm),
            "cpu_pct":        float(cfg.cpu_pct),
        }

    # ----- foreground helpers (NOT part of the Service protocol) -----------

    def is_purged(self) -> bool:
        return self._purged or self.engine.is_purged()

    def last_event(self) -> Optional[Event]:
        return self.engine.last_event()

    def snapshot(self) -> dict[str, object]:
        return self.engine.snapshot()


__all__ = ["MirageService"]
