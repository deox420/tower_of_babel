"""MIRAGE CLI front-end.

Subcommands::

    babel mirage                           # interactive Textual screen
    babel mirage start [knobs...]          # run engine until Ctrl+C / --duration
    babel mirage profiles                  # list profiles + envelopes
    babel mirage status                    # placeholder (per MASTER.md no on-disk state)
    babel mirage --setup                   # diagnostic

The ``start`` subcommand exits 0 on a clean stop, 1 if any request
warned (timeouts, 5xx), 2 on invocation errors, 3 on I/O issues
(control port unreachable when rotation was requested), and 5 if
Tor is unreachable and ``--clearnet`` was not passed.

Exit codes follow ``docs/tools/MIRAGE.md`` Section 4.  The ceilings
named in ``MAX_*`` below are validated at parse time so the engine
itself never sees a user-supplied value beyond the documented cap.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from typing import Sequence

from tools.mirage.engine import (
    EngineConfig, Event, HttpxTransport, MirageEngine,
)
from tools.mirage.profile import LOCALES, list_profiles


# Exit codes (MIRAGE.md Section 4).
EX_OK = 0
EX_WARN = 1
EX_USAGE = 2
EX_IO = 3
EX_CATALOG = 4
EX_TOR = 5


# Ceilings.  Match docs/tools/MIRAGE.md Section 4.
MAX_BW_KBPS = 4096
MAX_RATE_RPM = 240
MAX_CPU_PCT = 25.0
MAX_ROTATE_MIN = 1440
MAX_DURATION = 86400


_CLEARNET_BANNER = (
    "\n"
    "  ! CLEARNET MODE -- MIRAGE will not use Tor.\n"
    "    Your OS resolver and your ISP will see every host in the\n"
    "    selected profile catalogue, with timestamps.  The cover\n"
    "    traffic is still cover, but the link to YOU is not hidden.\n"
    "\n"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="babel mirage",
        description="cover traffic generator -- background HTTP noise over Tor",
    )
    p.add_argument("--setup", action="store_true",
                   help="diagnostic: httpx + Tor SOCKS5 + control port")
    sub = p.add_subparsers(dest="cmd")

    p_start = sub.add_parser("start", help="run the engine in the foreground")
    p_start.add_argument(
        "--profile", default="office_worker",
        choices=[s.name for s in list_profiles()],
    )
    p_start.add_argument("--locale", choices=LOCALES, default="en")
    p_start.add_argument("--bw-kbps", type=int, default=100,
                         help="bandwidth ceiling (KB/s); max 4096")
    p_start.add_argument("--rate-rpm", type=int, default=30,
                         help="request-rate ceiling per minute; max 240")
    p_start.add_argument("--cpu-pct", type=float, default=2.0,
                         help="CPU ceiling, 1-minute avg; max 25.0")
    p_start.add_argument("--rotate-min", type=int, default=0,
                         help="NEWNYM every N minutes (0=disable)")
    p_start.add_argument("--duration", type=int, default=0,
                         help="exit cleanly after N seconds (0=run forever)")
    p_start.add_argument("--clearnet", action="store_true",
                         help="bypass Tor (requires --i-know)")
    p_start.add_argument("--i-know", action="store_true",
                         help="confirm that you accept the clearnet warning")
    p_start.add_argument("--honest", action="store_true",
                         help="print each request to stderr as it fires")
    p_start.add_argument("--json", action="store_true",
                         help="emit a JSON line per request to stderr")
    p_start.add_argument("--dry-run", type=int, metavar="N", default=0,
                         help="plan and print N requests; do not send any")

    sub.add_parser("profiles", help="list profiles and their envelopes")
    sub.add_parser("status", help="show engine state (note: no on-disk state)")

    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.setup:
        from tools.mirage.setup_check import run as setup_run
        code, lines = setup_run()
        for line in lines:
            sys.stdout.write(line + "\n")
        return code

    if args.cmd is None:
        return _run_interactive()
    if args.cmd == "profiles":
        return _cmd_profiles()
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "start":
        return _cmd_start(args)

    parser.print_help()
    return EX_USAGE


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------


def _cmd_profiles() -> int:
    for spec in list_profiles():
        low, high = spec.rpm_typical
        sys.stdout.write(
            f"  {spec.name:<16}  {spec.description:<46}  "
            f"{low}-{high} rpm typical\n"
        )
    return EX_OK


def _cmd_status() -> int:
    # The status subcommand exists for symmetry with the other tools'
    # diagnostics.  MIRAGE keeps no on-disk state, so a fresh process
    # has nothing to report; the in-chrome service has live state but
    # is reached via the TUI, not this CLI.
    sys.stdout.write(
        "mirage: no live engine in this process.\n"
        "        Use `babel mirage start` to run, or open the TUI\n"
        "        with `babel mirage` to register a service slot.\n"
    )
    return EX_OK


def _cmd_start(args: argparse.Namespace) -> int:
    # --- validate ceilings ---
    err = _validate_ceilings(args)
    if err is not None:
        sys.stderr.write(err + "\n")
        return EX_USAGE

    use_tor = not args.clearnet
    if args.clearnet:
        if not args.i_know:
            sys.stderr.write(_CLEARNET_BANNER)
            sys.stderr.write(
                "mirage: --clearnet bypasses Tor. Re-run with --i-know to confirm.\n"
            )
            return EX_USAGE
        sys.stderr.write(_CLEARNET_BANNER)

    config = EngineConfig(
        profile=args.profile,
        locale=args.locale,
        bw_kbps=args.bw_kbps,
        rate_rpm=args.rate_rpm,
        cpu_pct=args.cpu_pct,
        rotate_min=args.rotate_min,
        use_tor=use_tor,
        honest=args.honest,
        duration_sec=args.duration,
    )

    # --- dry run? plan and stop. -------------------------------------------
    if args.dry_run and args.dry_run > 0:
        from tools.mirage.engine import MirageEngine

        class _NullTransport:
            name = "null"
            async def fetch(self, host, path, headers): ...
            async def close(self): pass
            async def rebuild(self): pass

        engine = MirageEngine(config=config, transport=_NullTransport())
        planned = engine.plan(min(args.dry_run, 1024))
        if args.json:
            for p in planned:
                sys.stdout.write(json.dumps({
                    "host": p.host, "path": p.path, "rank": p.rank,
                }) + "\n")
        else:
            for p in planned:
                sys.stdout.write(
                    f"  GET https://{p.host}{p.path}    (rank {p.rank})\n"
                )
        return EX_OK

    # --- live run ----------------------------------------------------------
    try:
        transport = HttpxTransport(use_tor=use_tor)
    except RuntimeError as e:
        sys.stderr.write(f"mirage: {e}\n")
        return EX_TOR
    except ImportError:
        sys.stderr.write("mirage: httpx not installed; run `babel mirage --setup`\n")
        return EX_USAGE

    def emit(ev: Event) -> None:
        if args.honest or args.json:
            from datetime import datetime, timezone
            ts = datetime.fromtimestamp(ev.ts_unix, tz=timezone.utc).strftime("%H:%M:%S UTC")
            if args.json:
                sys.stderr.write(json.dumps({
                    "ts": ev.ts_unix, "host": ev.host, "path": ev.path,
                    "bytes": ev.bytes_in, "ms": round(ev.duration_ms, 1),
                    "status": ev.status, "error": ev.error,
                }) + "\n")
                sys.stderr.flush()
            else:
                err = f"  ERROR {ev.error}" if ev.error else ""
                sys.stderr.write(
                    f"[{ts}] GET https://{ev.host}{ev.path}  "
                    f"{ev.bytes_in / 1024:6.1f} KB  "
                    f"{ev.duration_ms:6.0f} ms{err}\n"
                )
                sys.stderr.flush()

    engine = MirageEngine(config=config, transport=transport, on_event=emit)

    sys.stderr.write(
        f"mirage: profile={config.profile}  "
        f"bw<={config.bw_kbps} KB/s  "
        f"rate<={config.rate_rpm} rpm  "
        f"cpu<={config.cpu_pct}%  "
        f"via {'tor' if use_tor else 'CLEARNET'}\n"
    )

    return asyncio.run(_run_engine(engine))


async def _run_engine(engine: MirageEngine) -> int:
    """Run an engine until Ctrl+C or its duration expires."""
    loop = asyncio.get_running_loop()
    stop_signal = asyncio.Event()

    def _on_sig() -> None:
        stop_signal.set()

    try:
        loop.add_signal_handler(signal.SIGINT, _on_sig)
        try:
            loop.add_signal_handler(signal.SIGTERM, _on_sig)
        except (NotImplementedError, RuntimeError):
            # Windows / restricted env: SIGTERM may not be supported.
            pass
    except (NotImplementedError, RuntimeError):
        # Some loops (e.g. Proactor on Windows) do not support signal
        # handlers at all; fall back to relying on KeyboardInterrupt.
        pass

    try:
        await engine.start()
    except RuntimeError as e:
        sys.stderr.write(f"mirage: {e}\n")
        return EX_TOR

    try:
        # Wait for either the engine to exit (duration / error) or for a signal.
        engine_task = asyncio.create_task(_wait_for_stop(engine, stop_signal))
        await engine_task
    except KeyboardInterrupt:
        stop_signal.set()
    finally:
        await engine.stop()

    snap = engine.snapshot()
    sys.stderr.write(
        f"mirage: shutdown clean  "
        f"({snap['requests']} requests, "
        f"{snap['bytes_in'] // 1024} KB, "
        f"{snap['error']} errors)\n"
    )
    if snap["warn"] or snap["error"]:
        return EX_WARN
    return EX_OK


async def _wait_for_stop(engine: MirageEngine, stop_signal: asyncio.Event) -> None:
    while engine.is_running():
        if stop_signal.is_set():
            return
        try:
            await asyncio.wait_for(stop_signal.wait(), timeout=0.5)
            return
        except asyncio.TimeoutError:
            continue


def _run_interactive() -> int:
    """Removed in v2.0.0 — interactive MIRAGE is reached via `babel`."""
    sys.stderr.write(
        "mirage: interactive MIRAGE is now part of the babel menu in v2.0.0.\n"
        "        run `babel` and pick `[5] MIRAGE`, or use "
        "`babel --exec mirage start --profile X` for scripting.\n"
    )
    return EX_USAGE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_ceilings(args: argparse.Namespace) -> str | None:
    if not (1 <= args.bw_kbps <= MAX_BW_KBPS):
        return f"mirage: --bw-kbps must be in 1..{MAX_BW_KBPS}"
    if not (1 <= args.rate_rpm <= MAX_RATE_RPM):
        return f"mirage: --rate-rpm must be in 1..{MAX_RATE_RPM}"
    if not (0.1 <= args.cpu_pct <= MAX_CPU_PCT):
        return f"mirage: --cpu-pct must be in 0.1..{MAX_CPU_PCT}"
    if args.rotate_min != 0 and not (1 <= args.rotate_min <= MAX_ROTATE_MIN):
        return f"mirage: --rotate-min must be 0 (disabled) or 1..{MAX_ROTATE_MIN}"
    if args.duration < 0 or args.duration > MAX_DURATION:
        return f"mirage: --duration must be 0..{MAX_DURATION}"
    return None


if __name__ == "__main__":
    raise SystemExit(main())
