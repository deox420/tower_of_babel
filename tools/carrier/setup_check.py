"""CARRIER diagnostic -- contributes to ``babel --setup``."""
from __future__ import annotations

from babel import theme


def run() -> tuple[int, list[str]]:
    g_ok = theme.glyph("active")
    g_warn = theme.glyph("warn")

    lines: list[str] = ["CARRIER -- steganography"]
    exit_code = 0

    try:
        import PIL  # noqa: F401
        version = getattr(PIL, "__version__", "?")
        lines.append(f"  {g_ok} PNG covers (Pillow {version})")
    except ImportError:
        lines.append(f"  {g_warn} PNG covers disabled: install Pillow>=10")
        exit_code = 1

    lines.append(f"  {g_ok} WAV covers (stdlib wave)")

    try:
        import argon2  # noqa: F401
        version = getattr(argon2, "__version__", "?")
        lines.append(f"  {g_ok} Argon2id KDF (argon2-cffi {version})")
    except ImportError:
        lines.append(f"  {g_warn} KDF disabled: install argon2-cffi>=23")
        exit_code = 1

    try:
        from shared.crypto.secure_mem import mlock_status
        status = mlock_status()
        if status.get("mlock_ok"):
            lines.append(f"  {g_ok} mlock OK -- AES keys pinned in RAM")
        else:
            reason = status.get("reason") or "unknown"
            lines.append(f"  {g_warn} mlock fallback ({reason}); "
                         f"keys live in plain bytearray pages")
    except Exception as e:
        lines.append(f"  {g_warn} mlock status unknown: {e}")

    return exit_code, lines


__all__ = ["run"]
