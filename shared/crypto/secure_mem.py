"""Memory locking + swap detection.

``SecureBytes`` allocates an anonymous, mlock'd buffer for long-lived
secrets (Ed25519 IK seed; padded plaintexts kept across `/burn`
timers). It falls back to a plain ``bytearray`` when mlock is denied
(Termux without root, hardened kernels, sandbox); we log once and keep
running. We make no claim about ratchet-internal state, which lives in
``doubleratchet``/``x3dh`` and is best-effort cleaned on ``/leave``.

Cross-platform:
    Linux/macOS/Termux : ctypes.mmap + mlock(2)
    Windows            : VirtualAlloc + VirtualLock
"""
from __future__ import annotations

import ctypes
import platform
import subprocess
import sys
import threading
from typing import Optional


_LOCK = threading.Lock()
_WARNED = False
MLOCK_OK: bool = True   # set to False the first time a lock call fails
MLOCK_REASON: str = ""


# ---------------------------------------------------------------------------
# Platform back-ends
# ---------------------------------------------------------------------------


_IS_WINDOWS = sys.platform == "win32"
_IS_MAC = sys.platform == "darwin"


if not _IS_WINDOWS:
    try:
        _libc = ctypes.CDLL(None, use_errno=True)
        _libc.mlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        _libc.mlock.restype = ctypes.c_int
        _libc.munlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        _libc.munlock.restype = ctypes.c_int
    except Exception:
        _libc = None
else:
    _libc = None
    try:
        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        _kernel32.VirtualAlloc.restype = ctypes.c_void_p
        _kernel32.VirtualAlloc.argtypes = [
            ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong
        ]
        _kernel32.VirtualFree.restype = ctypes.c_bool
        _kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
        _kernel32.VirtualLock.restype = ctypes.c_bool
        _kernel32.VirtualLock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
        _kernel32.VirtualUnlock.restype = ctypes.c_bool
        _kernel32.VirtualUnlock.argtypes = [ctypes.c_void_p, ctypes.c_size_t]
    except Exception:
        _kernel32 = None


_MEM_COMMIT = 0x1000
_MEM_RESERVE = 0x2000
_MEM_RELEASE = 0x8000
_PAGE_READWRITE = 0x04


def _warn_once(reason: str) -> None:
    global _WARNED, MLOCK_OK, MLOCK_REASON
    with _LOCK:
        MLOCK_OK = False
        MLOCK_REASON = reason
        if _WARNED:
            return
        _WARNED = True
    try:
        sys.stderr.write(
            "WARNING: mlock unavailable, keys may touch swap if swap is enabled "
            f"({reason})\n"
        )
        sys.stderr.flush()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# SecureBytes
# ---------------------------------------------------------------------------


class SecureBytes:
    """Best-effort locked, zero-on-free byte buffer.

    Treat instances as write-once: `write(initial_bytes)` then
    `bytes()` for crypto operations, `zero()` (or context manager exit)
    to wipe. Memoryview access via `view()` for read-only-ish iteration.
    """

    __slots__ = ("_size", "_ptr", "_buf_ref", "_locked", "_freed", "_fallback")

    def __init__(self, size: int) -> None:
        if size <= 0:
            raise ValueError("size must be > 0")
        self._size = size
        self._ptr: Optional[int] = None
        self._buf_ref: Optional[bytearray] = None
        self._locked = False
        self._freed = False
        self._fallback = False
        self._allocate()

    # ---- platform-specific allocation -------------------------------------

    def _allocate(self) -> None:
        if _IS_WINDOWS and _kernel32 is not None:
            ptr = _kernel32.VirtualAlloc(
                None, self._size, _MEM_COMMIT | _MEM_RESERVE, _PAGE_READWRITE
            )
            if not ptr:
                self._fallback_alloc("VirtualAlloc failed")
                return
            if not _kernel32.VirtualLock(ptr, self._size):
                _kernel32.VirtualFree(ptr, 0, _MEM_RELEASE)
                self._fallback_alloc("VirtualLock denied")
                return
            self._ptr = int(ptr)
            self._locked = True
            ctypes.memset(self._ptr, 0, self._size)
            return

        if _libc is not None:
            try:
                import mmap as _mmap
                buf = _mmap.mmap(
                    -1, self._size,
                    flags=_mmap.MAP_PRIVATE | _mmap.MAP_ANONYMOUS,
                    prot=_mmap.PROT_READ | _mmap.PROT_WRITE,
                )
                # Pin the mmap so it isn't GC'd while we hold the pointer.
                self._buf_ref = buf  # type: ignore[assignment]
                ptr = ctypes.addressof(ctypes.c_char.from_buffer(buf))
                if _libc.mlock(ptr, self._size) != 0:
                    err = ctypes.get_errno()
                    self._fallback_alloc(f"mlock errno={err}")
                    try:
                        buf.close()
                    except Exception:
                        pass
                    self._buf_ref = None
                    return
                self._ptr = int(ptr)
                self._locked = True
                ctypes.memset(self._ptr, 0, self._size)
                return
            except Exception as e:
                self._fallback_alloc(f"mmap failed: {type(e).__name__}")
                return

        self._fallback_alloc("no platform mlock available")

    def _fallback_alloc(self, reason: str) -> None:
        _warn_once(reason)
        self._fallback = True
        self._buf_ref = bytearray(self._size)
        self._ptr = None
        self._locked = False

    # ---- write/read --------------------------------------------------------

    def write(self, data: bytes, offset: int = 0) -> None:
        if self._freed:
            raise RuntimeError("SecureBytes already freed")
        if offset < 0 or offset + len(data) > self._size:
            raise ValueError("write out of bounds")
        if self._fallback:
            for i, b in enumerate(data):
                self._buf_ref[offset + i] = b
            return
        assert self._ptr is not None
        ctypes.memmove(self._ptr + offset, data, len(data))

    def bytes(self) -> bytes:
        """Returns a transient bytes copy. Caller is responsible for not retaining it."""
        if self._freed:
            raise RuntimeError("SecureBytes already freed")
        if self._fallback:
            return bytes(self._buf_ref)
        assert self._ptr is not None
        return ctypes.string_at(self._ptr, self._size)

    def zero(self) -> None:
        if self._freed:
            return
        if self._fallback:
            for i in range(len(self._buf_ref)):
                self._buf_ref[i] = 0
            return
        if self._ptr is not None:
            ctypes.memset(self._ptr, 0, self._size)

    def free(self) -> None:
        if self._freed:
            return
        self.zero()
        if self._fallback:
            self._buf_ref = None
        else:
            if _IS_WINDOWS and self._locked and self._ptr is not None and _kernel32 is not None:
                try:
                    _kernel32.VirtualUnlock(self._ptr, self._size)
                    _kernel32.VirtualFree(self._ptr, 0, _MEM_RELEASE)
                except Exception:
                    pass
            elif _libc is not None and self._locked and self._ptr is not None:
                try:
                    _libc.munlock(self._ptr, self._size)
                except Exception:
                    pass
                if self._buf_ref is not None:
                    try:
                        self._buf_ref.close()  # type: ignore[union-attr]
                    except Exception:
                        pass
                    self._buf_ref = None
            self._ptr = None
        self._freed = True

    # ---- context manager ---------------------------------------------------

    def __enter__(self) -> "SecureBytes":
        return self

    def __exit__(self, *exc) -> None:
        self.free()

    def __del__(self) -> None:
        try:
            self.free()
        except Exception:
            pass

    # ---- info --------------------------------------------------------------

    @property
    def locked(self) -> bool:
        return self._locked

    def __len__(self) -> int:
        return self._size


# ---------------------------------------------------------------------------
# Swap detection
# ---------------------------------------------------------------------------


def swap_active() -> bool:
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/swaps", "r", encoding="utf-8", errors="ignore") as f:
                lines = [ln for ln in f.read().splitlines() if ln.strip()]
            # Header is always present; >1 lines = at least one swap area.
            return len(lines) > 1
        if _IS_MAC:
            out = subprocess.run(
                ["sysctl", "-n", "vm.swapusage"],
                capture_output=True, text=True, timeout=2, check=False,
            )
            if out.returncode == 0 and "used =" in out.stdout:
                # used = 0.00M usually means swap configured but unused; still risky.
                # treat configured-and-non-zero-total as active.
                # Format: "total = 2048.00M used = 12.00M free = 2036.00M ..."
                line = out.stdout.strip()
                tokens = line.split()
                # find "total =" and parse the value
                for i, t in enumerate(tokens):
                    if t == "total" and i + 2 < len(tokens):
                        val = tokens[i + 2]
                        try:
                            num = float(val.rstrip("KMGT"))
                            return num > 0
                        except ValueError:
                            pass
            return False
        if _IS_WINDOWS:
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management",
                )
                val, _ = winreg.QueryValueEx(key, "PagingFiles")
                winreg.CloseKey(key)
                if isinstance(val, list):
                    val = "\n".join(val)
                return bool(val and val.strip() and val.strip().lower() != "(empty)")
            except Exception:
                return False
        return False
    except Exception:
        return False


def mlock_status() -> dict:
    return {
        "mlock_ok": MLOCK_OK,
        "swap_active": swap_active(),
        "reason": MLOCK_REASON,
        "platform": platform.system(),
    }


# ---------------------------------------------------------------------------
# Self-test on import: try a tiny lock to populate MLOCK_OK early.
# ---------------------------------------------------------------------------


def _probe() -> None:
    try:
        buf = SecureBytes(64)
        buf.free()
    except Exception as e:
        _warn_once(f"probe failed: {type(e).__name__}")


_probe()
