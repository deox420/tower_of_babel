"""``void --setup`` — interactive diagnostic. Writes nothing to disk."""
from __future__ import annotations

import os
import socket
import sys

from . import secure_mem


TOR_DEFAULT_HOST = "127.0.0.1"
TOR_DEFAULT_PORT = 9050
TOR_SOCKS_CANDIDATES = [9050, 9150, 9151]   # system Tor / Tor Browser / TBB legacy


def probe_tor(host: str = TOR_DEFAULT_HOST, port: int = TOR_DEFAULT_PORT, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def detect_socks_port(host: str = TOR_DEFAULT_HOST, timeout: float = 1.0) -> int | None:
    """Find the first reachable Tor SOCKS5 port. Returns None if none."""
    for port in TOR_SOCKS_CANDIDATES:
        if probe_tor(host, port, timeout):
            return port
    return None


def colour_supported() -> bool:
    if "COLORTERM" in os.environ:
        return True
    term = os.environ.get("TERM", "")
    return any(term.endswith(s) or s in term for s in ("256color", "truecolor", "xterm", "screen"))


def install_hint() -> str:
    if sys.platform == "darwin":
        return "brew install tor"
    if sys.platform == "win32":
        return "download Tor Browser (it bundles a SOCKS5 proxy on 9150)"
    if "ANDROID_ROOT" in os.environ or os.path.exists("/data/data/com.termux"):
        return "pkg install tor && tor &"
    return "sudo apt install tor    # or: sudo dnf install tor / pacman -S tor"


def run() -> int:
    out = sys.stdout
    out.write("\nVOID setup check\n================\n")

    socks = detect_socks_port()
    tor_ok = socks is not None
    if tor_ok:
        out.write(f"  Tor SOCKS5: OK on 127.0.0.1:{socks}\n")
    else:
        out.write(f"  Tor SOCKS5: not detected (tried {TOR_SOCKS_CANDIDATES})\n")

    status = secure_mem.mlock_status()
    out.write(f"  mlock available:                  ")
    out.write("OK\n" if status["mlock_ok"] else f"FAIL ({status['reason']})\n")

    out.write(f"  swap active:                      ")
    out.write("yes\n" if status["swap_active"] else "no\n")

    out.write(f"  terminal:                         ")
    if colour_supported():
        out.write(f"OK (TERM={os.environ.get('TERM', '?')})\n")
    else:
        out.write(f"limited colours (TERM={os.environ.get('TERM', '?')})\n")

    out.write(f"  platform:                         {sys.platform} ({status['platform']})\n")
    out.write(f"  python:                           {sys.version.split()[0]}\n")

    out.write("\nrecommendation:\n")
    if not tor_ok:
        out.write(f"  start Tor first: {install_hint()}\n")
    if not status["mlock_ok"] and status["swap_active"]:
        out.write("  swap is active and memory locking failed.\n")
        out.write("  Keys may touch disk. Disable swap or run with reduced trust.\n")
    if tor_ok and (status["mlock_ok"] or not status["swap_active"]):
        out.write("  ready to run: void --onion <addr.onion:8765>\n")
    out.write("\n")
    return 0 if tor_ok else 1
