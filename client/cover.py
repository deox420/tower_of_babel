"""Cover traffic background task.

The task wakes every 15-45s and sends a DUMMY message ONLY if no real
message was sent during that interval. Real sends cancel the upcoming
dummy by bumping a counter that the loop checks against its snapshot.
"""
from __future__ import annotations

import asyncio
import random
from typing import Callable, Awaitable

COVER_MIN_SEC = 15.0
COVER_MAX_SEC = 45.0


class CoverTraffic:
    def __init__(self, send_dummy: Callable[[], Awaitable[None]]) -> None:
        self._send_dummy = send_dummy
        self._real_count = 0
        self._task: asyncio.Task | None = None
        self._stopped = asyncio.Event()

    def note_real_send(self) -> None:
        self._real_count += 1

    def start(self) -> None:
        if self._task is None:
            self._stopped.clear()
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None

    async def _loop(self) -> None:
        try:
            while not self._stopped.is_set():
                interval = random.uniform(COVER_MIN_SEC, COVER_MAX_SEC)
                marker = self._real_count
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=interval)
                    return  # stopped before interval elapsed
                except asyncio.TimeoutError:
                    pass
                if self._stopped.is_set():
                    return
                if self._real_count == marker:
                    try:
                        await self._send_dummy()
                    except Exception:
                        pass
        except asyncio.CancelledError:
            return
