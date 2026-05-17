"""MIRAGE diagnostic -- contributes to ``babel --setup``.

Verifies that the runtime pieces MIRAGE depends on are present:

- httpx (shared with MASK; MIRAGE is the second consumer)
- Tor SOCKS5 reachability (informational; clearnet still works)
- Tor control port (informational; only used by ``--rotate-min``)
- Profile catalogs load cleanly (would only fail under tampering)
"""
from __future__ import annotations

import asyncio

from babel import theme


def run() -> tuple[int, list[str]]:
    g_ok = theme.glyph("active")
    g_warn = theme.glyph("warn")

    lines: list[str] = ["MIRAGE -- cover traffic generator"]
    exit_code = 0

    try:
        import httpx  # noqa: F401
        version = getattr(httpx, "__version__", "?")
        lines.append(f"  {g_ok} HTTP transport (httpx {version})")
    except ImportError:
        lines.append(f"  {g_warn} MIRAGE disabled: install 'httpx[socks]>=0.27'")
        exit_code = 1

    try:
        from shared.tor.socks_detect import detect_socks_port
        port = detect_socks_port()
        if port is not None:
            lines.append(f"  {g_ok} Tor SOCKS5 reachable on 127.0.0.1:{port}")
        else:
            lines.append(f"  {g_warn} Tor SOCKS5 not reachable -- "
                         f"clearnet still works with --clearnet --i-know")
    except Exception as e:
        lines.append(f"  {g_warn} Tor probe failed: {e}")

    # Control port -- optional; only matters when the user wants NEWNYM.
    try:
        from shared.tor.control import TorControl
        try:
            tc = asyncio.run(TorControl.connect())
            try:
                asyncio.run(tc.close())
            except Exception:
                pass
            lines.append(f"  {g_ok} Tor control port reachable (NEWNYM available)")
        except Exception:
            lines.append(f"  {g_warn} Tor control port unreachable -- "
                         f"--rotate-min will be a no-op")
    except Exception as e:
        lines.append(f"  {g_warn} control-port probe failed: {e}")

    # Profile catalog sanity (would only fail under tampering, but cheap to check).
    try:
        from tools.mirage.profile import PROFILES, list_profiles
        from tools.mirage.sites import PROFILE_SITES
        for spec in list_profiles():
            if spec.sites_key not in PROFILE_SITES:
                lines.append(f"  {g_warn} profile {spec.name} has no catalog")
                exit_code = 1
            elif not PROFILE_SITES[spec.sites_key]:
                lines.append(f"  {g_warn} profile {spec.name} catalog empty")
                exit_code = 1
        lines.append(
            f"  {g_ok} {len(PROFILES)} profiles loaded "
            f"({', '.join(sorted(PROFILES))})"
        )
    except Exception as e:
        lines.append(f"  {g_warn} profile registry malformed: {e}")
        exit_code = 1

    return exit_code, lines


__all__ = ["run"]
