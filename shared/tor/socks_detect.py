"""Detect a reachable Tor SOCKS5 port on the local machine.

Used by every tool that routes through Tor: VOID (chat), MASK
(temp-mail over Tor), MIRAGE (cover traffic via fresh circuits).
The detection is a plain TCP connect with a short timeout; we
do not speak SOCKS5 here. If the port answers, we trust the
SOCKS5 handshake to surface any deeper issues at use time.

Ports tried, in order:
    9050   - system Tor (Debian, Arch, Fedora, Homebrew, Termux)
    9150   - Tor Browser bundle (current)
    9151   - Tor Browser bundle (legacy)

See MASTER.md Section 5.4.
"""
from __future__ import annotations

import socket


TOR_DEFAULT_HOST = "127.0.0.1"
TOR_DEFAULT_PORT = 9050
TOR_SOCKS_CANDIDATES = [9050, 9150, 9151]   # system Tor / Tor Browser / TBB legacy


def probe_tor(
    host: str = TOR_DEFAULT_HOST,
    port: int = TOR_DEFAULT_PORT,
    timeout: float = 2.0,
) -> bool:
    """Return True iff a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_socks_port(
    host: str = TOR_DEFAULT_HOST,
    timeout: float = 1.0,
) -> int | None:
    """Find the first reachable Tor SOCKS5 port. Returns None if none answer."""
    for port in TOR_SOCKS_CANDIDATES:
        if probe_tor(host, port, timeout):
            return port
    return None
