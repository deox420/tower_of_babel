"""MASK diagnostic -- contributes to ``babel --setup``.

Verifies:
- Pillow (avatar rasterisation)
- argon2-cffi (encrypted export)
- httpx (mail adapters)
- mlock status (passphrase wrappers)
- Tor SOCKS5 reachability (informational; clearnet still works)
"""
from __future__ import annotations

from babel import theme


def run() -> tuple[int, list[str]]:
    g_ok = theme.glyph("active")
    g_warn = theme.glyph("warn")

    lines: list[str] = ["MASK -- disposable identity generator"]
    exit_code = 0

    try:
        import PIL  # noqa: F401
        version = getattr(PIL, "__version__", "?")
        lines.append(f"  {g_ok} avatar render (Pillow {version})")
    except ImportError:
        lines.append(f"  {g_warn} avatar disabled: install Pillow>=10")
        exit_code = 1

    try:
        import argon2  # noqa: F401
        # argon2.__version__ was deprecated in argon2-cffi 23.x; the
        # supported lookup is importlib.metadata which queries the
        # installed package's PKG-INFO.
        try:
            from importlib.metadata import version as _pkg_version
            version = _pkg_version("argon2-cffi")
        except Exception:
            version = "?"
        lines.append(f"  {g_ok} encrypted export (argon2-cffi {version})")
    except ImportError:
        lines.append(f"  {g_warn} export disabled: install argon2-cffi>=23")
        exit_code = 1

    try:
        import httpx  # noqa: F401
        version = getattr(httpx, "__version__", "?")
        lines.append(f"  {g_ok} temp-mail (httpx {version})")
    except ImportError:
        lines.append(f"  {g_warn} mail disabled: install 'httpx[socks]>=0.27'")
        exit_code = 1

    try:
        from shared.crypto.secure_mem import mlock_status
        status = mlock_status()
        if status.get("mlock_ok"):
            lines.append(f"  {g_ok} mlock OK -- passphrase pinned in RAM")
        else:
            reason = status.get("reason") or "unknown"
            lines.append(f"  {g_warn} mlock fallback ({reason}); "
                         f"passphrase lives in plain bytearray pages")
    except Exception as e:
        lines.append(f"  {g_warn} mlock status unknown: {e}")

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

    return exit_code, lines


__all__ = ["run"]
