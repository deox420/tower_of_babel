"""The MIRAGE request engine.

The engine is an async loop that:

  1. Plans the next outgoing fetch using ``schedule.zipf_draw`` and
     the configured profile.
  2. Gates it through two ``TokenBucket``s -- one for bytes/s, one
     for requests/min.  If either bucket is short, the engine sleeps
     until the deficit fills.
  3. Issues the request through a ``Transport`` (an injected
     interface, so tests can run without httpx and the chrome can
     run with).
  4. Records the (timestamp, host, bytes, ms, status) event in a
     bounded ring buffer.
  5. Optionally signals ``NEWNYM`` to the Tor control port every
     ``rotate_min`` minutes; on rotation the HTTP client is rebuilt
     so per-host TLS sessions do not survive.

State is fully in-memory.  ``stop()`` cancels the loop, closes the
client, and resets all buckets.  No on-disk writes anywhere.

See ``docs/tools/MIRAGE.md`` Section 2 for the protection contract
each piece honours; ``pentest/mirage/`` proves each row holds.
"""
from __future__ import annotations

import asyncio
import collections
import dataclasses
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

from shared.tor.socks_detect import detect_socks_port

from tools.mirage.caps import CpuMeter, TokenBucket
from tools.mirage.profile import ProfileSpec, get_profile
from tools.mirage.schedule import PlannedFetch, dwell_for, zipf_draw
from tools.mirage.sites import get_catalog


# ---------------------------------------------------------------------------
# Transport (injected; httpx implementation in this module, mock in pentest).
# ---------------------------------------------------------------------------

class Transport(Protocol):
    """Bare-minimum interface the engine asks of an HTTP client.

    Implementations live or die by these two methods.  The real
    ``HttpxTransport`` wraps an ``httpx.AsyncClient``; pentest fakes
    record calls and return canned results.  Either way, the engine
    code does not change.
    """

    name: str

    async def fetch(self, host: str, path: str, headers: dict[str, str]
                    ) -> "FetchResult": ...

    async def close(self) -> None: ...

    async def rebuild(self) -> None: ...


@dataclass
class FetchResult:
    host: str
    path: str
    status: int
    bytes_in: int
    duration_ms: float
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and 200 <= self.status < 400


# ---------------------------------------------------------------------------
# Event log
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Event:
    ts_unix: float
    host: str
    path: str
    bytes_in: int
    duration_ms: float
    status: int
    error: str | None = None


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class EngineConfig:
    """User-facing knobs.  Defaults match ``docs/tools/MIRAGE.md`` Section 4.

    ``rotate_min == 0`` disables circuit rotation entirely.  This is
    the default because every NEWNYM is itself an observable signal
    (see Section 3 of the docs).
    """

    profile: str = "office_worker"
    locale: str = "en"
    bw_kbps: int = 100
    rate_rpm: int = 30
    cpu_pct: float = 2.0
    rotate_min: int = 0
    use_tor: bool = True
    honest: bool = False
    duration_sec: int = 0   # 0 = run until stopped
    log_capacity: int = 256
    # The engine reads its own clock by default but tests override via
    # ``time_fn``; ditto for ``rng``.  Keep both injectable here.
    time_fn: Callable[[], float] = field(default=time.monotonic)
    rng_seed: int | None = None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class MirageEngine:
    """Async request loop with bandwidth + rate + cpu caps.

    Lifecycle::

        engine = MirageEngine(config, transport)
        await engine.start()        # spawns the loop
        ...                         # foreground UI can call engine.snapshot()
        await engine.stop()         # cancels + closes; idempotent

    The engine is single-task; ``start()`` returns immediately and
    the loop runs as an asyncio Task on the engine's event loop.
    ``stop()`` is safe to call from any other coroutine.
    """

    def __init__(
        self,
        config: EngineConfig,
        transport: Transport,
        on_event: Callable[[Event], None] | None = None,
    ) -> None:
        self.config = config
        self.transport = transport
        self._on_event = on_event
        self._task: asyncio.Task[None] | None = None
        self._stopped = asyncio.Event()
        self._paused = False
        self._rng = random.Random(config.rng_seed)
        self._profile: ProfileSpec = get_profile(config.profile)
        self._catalog = get_catalog(self._profile.sites_key)
        # Bandwidth cap: capacity ~ one second of credit; refill = bytes/sec.
        bps = max(1.0, config.bw_kbps * 1024.0)
        self._bw_bucket = TokenBucket(capacity=bps, refill_per_sec=bps)
        # Rate cap: capacity ~ ``rate_rpm`` requests held over 60s; refill = per-sec.
        rps = max(1.0 / 60.0, config.rate_rpm / 60.0)
        self._rate_bucket = TokenBucket(
            capacity=max(1.0, float(config.rate_rpm)),
            refill_per_sec=rps,
        )
        self._cpu = CpuMeter(window_sec=60.0)
        self._cpu_last_sample_pt: float | None = None   # process_time at last sample
        self._cpu_last_sample_wt: float | None = None   # wall time at last sample
        self._log: collections.deque[Event] = collections.deque(
            maxlen=max(16, config.log_capacity)
        )
        self._counters = {
            "requests": 0,
            "ok": 0,
            "warn": 0,
            "error": 0,
            "bytes_in": 0,
        }
        self._started_at: float | None = None
        self._last_event_at: float | None = None
        self._last_rotation_at: float | None = None
        self._purged: bool = False

    # ----- public lifecycle -------------------------------------------------

    async def start(self) -> None:
        """Spawn the async request loop.

        Raises ``RuntimeError`` if Tor is required and not reachable,
        or if the engine has already been started.
        """
        if self._task is not None:
            raise RuntimeError("mirage engine already started")
        if self.config.use_tor:
            port = detect_socks_port(timeout=1.0)
            if port is None:
                raise RuntimeError(
                    "Tor SOCKS5 not reachable on 9050 / 9150 / 9151; "
                    "either start Tor or pass --clearnet --i-know"
                )
        self._stopped.clear()
        self._started_at = self.config.time_fn()
        self._task = asyncio.create_task(self._run(), name="mirage-engine")

    async def stop(self) -> None:
        """Cancel the loop, close the transport, reset caps.

        Idempotent.  The chrome's ``purge_local`` calls this and
        expects it to return inside one second.
        """
        if self._purged:
            return
        self._stopped.set()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=0.75)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass
            except Exception:
                pass
        try:
            await asyncio.wait_for(self.transport.close(), timeout=0.5)
        except Exception:
            pass
        self._bw_bucket.reset()
        self._rate_bucket.reset()
        self._cpu.reset()
        self._purged = True

    def pause(self) -> None:
        """Stop issuing requests until ``resume()`` is called."""
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # ----- public introspection --------------------------------------------

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def is_purged(self) -> bool:
        return self._purged

    def snapshot(self) -> dict[str, object]:
        """Static view of engine state for the UI / pentest assertions."""
        now = self.config.time_fn()
        uptime = (now - self._started_at) if self._started_at else 0.0
        return {
            "profile": self._profile.name,
            "locale": self.config.locale,
            "running": self.is_running(),
            "paused": self._paused,
            "purged": self._purged,
            "uptime_sec": uptime,
            "bw_kbps": self.config.bw_kbps,
            "rate_rpm": self.config.rate_rpm,
            "cpu_pct": self.config.cpu_pct,
            "cpu_avg": self._cpu.average(now) * 100.0,
            "requests": self._counters["requests"],
            "ok": self._counters["ok"],
            "warn": self._counters["warn"],
            "error": self._counters["error"],
            "bytes_in": self._counters["bytes_in"],
        }

    def events(self, limit: int | None = None) -> list[Event]:
        """Most-recent-first list of ring-buffer events."""
        seq = list(self._log)
        seq.reverse()
        if limit is not None:
            seq = seq[: max(0, limit)]
        return seq

    def last_event(self) -> Event | None:
        if not self._log:
            return None
        return self._log[-1]

    # ----- dry-run planning -------------------------------------------------

    def plan(self, n: int) -> list[PlannedFetch]:
        """Return ``n`` upcoming fetches without sending anything.

        Used by ``babel mirage start --dry-run`` and by pentest.  The
        engine's RNG state advances; calling ``plan`` then ``start``
        gives a different sequence than calling ``start`` alone,
        which is intentional -- dry runs are an inspection tool, not
        a rehearsal.
        """
        return [zipf_draw(self._catalog, self._rng) for _ in range(max(0, n))]

    # ----- internal loop ----------------------------------------------------

    async def _run(self) -> None:
        try:
            while not self._stopped.is_set():
                if self.config.duration_sec > 0:
                    elapsed = self.config.time_fn() - (self._started_at or 0.0)
                    if elapsed >= self.config.duration_sec:
                        break

                if self._paused:
                    await asyncio.sleep(0.25)
                    continue

                await self._maybe_rotate()

                planned = zipf_draw(self._catalog, self._rng)
                await self._gate(planned)

                if self._stopped.is_set():
                    break
                if self._cpu_over_cap():
                    # Burn off cooldown by sleeping a full request budget.
                    await asyncio.sleep(min(2.0, 60.0 / max(1, self.config.rate_rpm)))
                    continue

                await self._issue(planned)

                # Inter-request dwell -- already lower-bounded by the rate cap.
                await asyncio.sleep(dwell_for(
                    self._profile, self.config.rate_rpm, self._rng,
                ))
        except asyncio.CancelledError:
            # Cooperative cancel from stop(); just exit.
            return

    async def _gate(self, planned: PlannedFetch) -> None:
        """Block until both buckets can pay for this fetch.

        The rate bucket pays one full request token (always exactly
        one); the bandwidth bucket has to wait *for any deficit
        carried by a previous oversized response* to pay back.
        ``MIN_NOMINAL`` (8 KiB) is the minimum credit the engine
        wants before firing.  The actual response cost is settled
        after the fetch via ``_settle_bandwidth``, which calls
        ``force_consume`` and is therefore allowed to drive the
        bucket negative -- the next ``_gate`` then sleeps long
        enough to pay back the deficit before firing the next
        request.  This makes the bucket a leaky integrator whose
        long-run average drain equals ``--bw-kbps``.
        """
        MIN_NOMINAL = 8 * 1024
        # Rate gate first -- cheaper to wait on.
        now = self.config.time_fn()
        wait = self._rate_bucket.time_until(1.0, now)
        if wait > 0:
            await asyncio.sleep(wait)
        # Bandwidth gate next: wait for any prior-fetch deficit to clear,
        # PLUS enough credit for a minimal next request.
        now = self.config.time_fn()
        wait = self._bw_bucket.time_until(MIN_NOMINAL, now)
        if wait > 0:
            await asyncio.sleep(wait)
        now = self.config.time_fn()
        # Rate is always one token per request and is small enough to
        # ``try_consume`` cleanly.  Bandwidth is charged at settle time
        # to keep the accounting honest (we do not know the size yet).
        self._rate_bucket.try_consume(1.0, now)

    def _settle_bandwidth(self, result: FetchResult) -> None:
        """Charge the actual response bytes to the bandwidth bucket.

        The bucket may go negative.  The next ``_gate`` then waits
        ``deficit / refill_per_sec`` seconds for the bucket to climb
        back above the minimum-nominal threshold, which is exactly
        what enforces the long-run rate.
        """
        if result.bytes_in <= 0:
            return
        now = self.config.time_fn()
        self._bw_bucket.force_consume(float(result.bytes_in), now)

    async def _issue(self, planned: PlannedFetch) -> None:
        cpu_t0 = time.process_time()
        headers = {
            "User-Agent": self._rng.choice(self._profile.user_agents),
            "Accept-Language": self._profile.language_for(self.config.locale),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        try:
            result = await self.transport.fetch(
                planned.host, planned.path, headers,
            )
        except Exception as e:
            result = FetchResult(
                host=planned.host, path=planned.path,
                status=0, bytes_in=0, duration_ms=0.0,
                error=str(e) or type(e).__name__,
            )

        self._settle_bandwidth(result)
        self._counters["requests"] += 1
        self._counters["bytes_in"] += max(0, result.bytes_in)
        if result.error:
            self._counters["error"] += 1
        elif not result.ok:
            self._counters["warn"] += 1
        else:
            self._counters["ok"] += 1

        ts = time.time()
        ev = Event(
            ts_unix=ts,
            host=result.host,
            path=result.path,
            bytes_in=result.bytes_in,
            duration_ms=result.duration_ms,
            status=result.status,
            error=result.error,
        )
        self._log.append(ev)
        self._last_event_at = self.config.time_fn()
        # Feed the CPU meter with the cost of this request.
        used = time.process_time() - cpu_t0
        self._cpu.observe(self.config.time_fn(), used)
        if self._on_event is not None:
            try:
                self._on_event(ev)
            except Exception:
                pass

    def _cpu_over_cap(self) -> bool:
        avg = self._cpu.average(self.config.time_fn())
        return avg * 100.0 > self.config.cpu_pct

    async def _maybe_rotate(self) -> None:
        if self.config.rotate_min <= 0:
            return
        now = self.config.time_fn()
        last = self._last_rotation_at or self._started_at or now
        interval = self.config.rotate_min * 60.0
        if (now - last) < interval:
            return
        await self.rotate_now()

    async def rotate_now(self) -> None:
        """Request a fresh Tor circuit and rebuild the HTTP client.

        Failures are non-fatal -- the engine logs the error event
        and proceeds with the existing circuit so a flaky control
        port does not stall the loop.
        """
        self._last_rotation_at = self.config.time_fn()
        try:
            await self.transport.rebuild()
        except Exception as e:
            self._log.append(Event(
                ts_unix=time.time(), host="(rotate)", path="",
                bytes_in=0, duration_ms=0.0, status=0,
                error=f"NEWNYM failed: {e}",
            ))


# ---------------------------------------------------------------------------
# Real transport (httpx + Tor control port for rotation).
# ---------------------------------------------------------------------------

class HttpxTransport:
    """Production transport: ``httpx.AsyncClient`` + optional NEWNYM.

    Imported lazily; the engine does not depend on httpx existing.
    Pentest swaps in a synthetic transport so the suite runs
    headless.
    """

    name = "httpx"

    def __init__(self, use_tor: bool, timeout_sec: float = 8.0) -> None:
        self._use_tor = use_tor
        self._timeout = timeout_sec
        self._client = self._build_client()

    def _build_client(self):
        import httpx  # local import; engine imports stay light
        proxy = None
        if self._use_tor:
            port = detect_socks_port(timeout=1.0)
            if port is None:
                raise RuntimeError(
                    "Tor SOCKS5 not reachable; cannot build httpx client"
                )
            proxy = f"socks5h://127.0.0.1:{port}"
        return httpx.AsyncClient(
            proxy=proxy,
            timeout=self._timeout,
            follow_redirects=False,
            http2=False,
        )

    async def fetch(self, host: str, path: str, headers: dict[str, str]) -> FetchResult:
        url = f"https://{host}{path}"
        t0 = time.perf_counter()
        try:
            r = await self._client.get(url, headers=headers)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            content = r.content or b""
            return FetchResult(
                host=host, path=path, status=r.status_code,
                bytes_in=len(content), duration_ms=elapsed_ms,
            )
        except Exception as e:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            return FetchResult(
                host=host, path=path, status=0,
                bytes_in=0, duration_ms=elapsed_ms,
                error=type(e).__name__,
            )

    async def close(self) -> None:
        try:
            await self._client.aclose()
        except Exception:
            pass

    async def rebuild(self) -> None:
        # 1. Ask the Tor control port for a NEWNYM (best effort).
        try:
            from shared.tor.control import TorControl
            tc = await TorControl.connect()
            try:
                info = await tc.protocol_info()
                await tc.authenticate(info)
                await tc._cmd("SIGNAL NEWNYM")
            finally:
                await tc.close()
        except Exception:
            # If we can't signal, still rebuild the client so the next
            # request lands on a fresh TCP / TLS handshake at least.
            pass
        # 2. Drop the existing client and open a new one.
        try:
            await self._client.aclose()
        except Exception:
            pass
        self._client = self._build_client()


__all__ = [
    "MirageEngine", "EngineConfig", "Transport", "FetchResult",
    "Event", "HttpxTransport",
]
