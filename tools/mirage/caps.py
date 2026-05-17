"""Rate-limiter primitives used by the MIRAGE engine.

Two pieces live here and they are intentionally pure-logic:

  * ``TokenBucket`` -- a leaky-bucket rate limiter parameterised by
    a refill rate and a capacity.  The engine passes wallclock time
    into every method; the bucket never reads the clock itself so
    every test can drive it deterministically.
  * ``CpuMeter`` -- a one-minute moving average of fractional CPU
    use, sampled by the caller.  Like the bucket it does not read
    any clock; the engine feeds ``observe(now, used)`` once per
    sample interval.

MIRAGE caps are documented in ``docs/tools/MIRAGE.md`` Section 2;
the defaults and ceilings are enforced one layer above in
``tools/mirage/cli.py``.  This module just provides the math.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Token bucket
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """Leaky-bucket rate limiter.

    ``capacity`` is the maximum credit the bucket holds; ``refill_per_sec``
    is the rate at which the bucket refills.  The bucket starts full
    (the caller can immediately consume up to ``capacity``); on a long
    idle gap the credit caps at ``capacity`` rather than growing
    unbounded -- that is what makes it a *bucket* and not a counter.
    """

    capacity: float
    refill_per_sec: float
    _level: float = field(init=False)
    _last: float | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        if self.capacity <= 0:
            raise ValueError("TokenBucket capacity must be > 0")
        if self.refill_per_sec <= 0:
            raise ValueError("TokenBucket refill_per_sec must be > 0")
        self._level = float(self.capacity)

    # ----- queries ----------------------------------------------------------

    @property
    def level(self) -> float:
        """Current credit (read-only)."""
        return self._level

    def _advance(self, now: float) -> None:
        if self._last is None:
            self._last = now
            return
        dt = now - self._last
        if dt < 0:
            # Clock went backwards (NTP skew, mocked clock in tests).
            # Do not credit negative time; just resync.
            self._last = now
            return
        self._level = min(self.capacity, self._level + dt * self.refill_per_sec)
        self._last = now

    def try_consume(self, amount: float, now: float) -> bool:
        """Attempt to consume ``amount`` credit; return True on success."""
        if amount <= 0:
            return True
        self._advance(now)
        if self._level >= amount:
            self._level -= amount
            return True
        return False

    def force_consume(self, amount: float, now: float) -> None:
        """Drain ``amount`` from the bucket unconditionally.

        Unlike ``try_consume``, this is allowed to drive ``_level``
        below zero -- the bucket then carries the deficit, and the
        next ``time_until`` call returns the wait needed to pay it
        back.  This is how MIRAGE's bandwidth gate handles responses
        that are larger than the bucket's capacity: charge the full
        cost, let the bucket go negative, and the engine sleeps
        proportionally on the next iteration.
        """
        if amount <= 0:
            return
        self._advance(now)
        self._level -= amount

    def time_until(self, amount: float, now: float) -> float:
        """How many seconds until ``amount`` credit will be available.

        Returns 0.0 if the credit is available right now.  The
        returned value assumes nobody else is draining the bucket
        in the meantime -- the engine treats it as a sleep duration
        and re-checks via ``try_consume`` after waking up.
        """
        if amount <= 0:
            return 0.0
        self._advance(now)
        if self._level >= amount:
            return 0.0
        deficit = amount - self._level
        return deficit / self.refill_per_sec

    def reset(self) -> None:
        """Refill to capacity and forget the last sample.  Used on purge."""
        self._level = float(self.capacity)
        self._last = None


# ---------------------------------------------------------------------------
# CPU meter
# ---------------------------------------------------------------------------

@dataclass
class CpuMeter:
    """Sliding one-minute average of fractional CPU.

    The caller samples its own CPU consumption (e.g. via
    ``time.process_time()``) on a regular interval and feeds the
    delta to ``observe(now, used_sec)``.  ``average()`` returns the
    sum of observed CPU-seconds divided by wallclock-seconds in the
    window.

    The class is profile-agnostic: it does not know what "the cap"
    is.  The engine compares ``average()`` to ``cpu_cap`` and decides
    to insert cooldown sleeps.
    """

    window_sec: float = 60.0
    _samples: deque = field(default_factory=deque, init=False)
    # Each sample is (now_wallclock, used_cpu_seconds_since_last_sample).

    def observe(self, now: float, used_sec: float) -> None:
        if used_sec < 0:
            return
        self._samples.append((now, float(used_sec)))
        self._evict(now)

    def _evict(self, now: float) -> None:
        cutoff = now - self.window_sec
        while self._samples and self._samples[0][0] < cutoff:
            self._samples.popleft()

    def average(self, now: float) -> float:
        """Fractional CPU averaged over the window (0.0 -- 1.0+).

        Returns 0.0 if no samples have been observed yet, or if the
        window length effectively collapses to zero (caller fed a
        single sample with no spread).
        """
        self._evict(now)
        if len(self._samples) < 2:
            return 0.0
        first = self._samples[0][0]
        elapsed = now - first
        if elapsed <= 0:
            return 0.0
        total = sum(used for _t, used in self._samples)
        return total / elapsed

    def reset(self) -> None:
        self._samples.clear()


__all__ = ["TokenBucket", "CpuMeter"]
