"""Direct Tor control-port client.

Speaks the Tor control-port protocol over async TCP without a
``stem`` dependency. Lifted out of VOID's original
``client/host.py`` so other tools (MIRAGE for NEW_CIRCUIT
requests, future room-style services for ADD_ONION) can use the
same code path.

Supported Tor authentication methods, in preference order:
  - cookie auth   (most Linux / macOS distros, Termux)
  - safe-cookie   (newer Tor)
  - null auth     (uncommon but allowed)
  - password auth (Tor Browser bundle on Windows) -- falls back to a
    clear error if a password is required and we do not have one.

The caller does NOT need to edit torrc as long as the control port
is already exposed. If it isn't, ``connect()`` raises
``TorControlError`` with a plain-English fix.
"""
from __future__ import annotations

import asyncio
import binascii
import hmac
import os
import secrets
from dataclasses import dataclass
from hashlib import sha256
from typing import Optional


CONTROL_PORTS = [9051, 9151]   # Tor (system) / Tor Browser bundle
COOKIE_PATHS = [
    "/run/tor/control.authcookie",
    "/var/run/tor/control.authcookie",
    "/usr/local/var/lib/tor/control_auth_cookie",
    "/opt/homebrew/var/lib/tor/control_auth_cookie",
    os.path.expanduser("~/.tor/control_auth_cookie"),
    os.path.expanduser("~/Library/Application Support/TorBrowser-Data/Tor/control_auth_cookie"),
    "/data/data/com.termux/files/usr/var/lib/tor/control_auth_cookie",
]


@dataclass
class TorInfo:
    auth_methods: list[str]
    cookie_file: Optional[str]
    version: str


class TorControlError(Exception):
    pass


class TorControl:
    """Minimal Tor control-port client (async)."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self.reader = reader
        self.writer = writer

    @classmethod
    async def connect(cls) -> "TorControl":
        last_err: Optional[Exception] = None
        for port in CONTROL_PORTS:
            try:
                r, w = await asyncio.open_connection("127.0.0.1", port)
                return cls(r, w)
            except OSError as e:
                last_err = e
        raise TorControlError(
            "Could not reach Tor's control port on 9051 or 9151. "
            "Add 'ControlPort 9051' and 'CookieAuthentication 1' to your torrc, "
            "then restart Tor. See README -> 'Hosting a server'."
        ) from last_err

    async def close(self) -> None:
        try:
            self.writer.write(b"QUIT\r\n")
            await self.writer.drain()
        except Exception:
            pass
        try:
            self.writer.close()
            await self.writer.wait_closed()
        except Exception:
            pass

    async def _cmd(self, line: str) -> list[str]:
        self.writer.write(line.encode("ascii") + b"\r\n")
        await self.writer.drain()
        out: list[str] = []
        while True:
            raw = await self.reader.readline()
            if not raw:
                raise TorControlError("Tor control connection closed mid-reply")
            text = raw.decode("ascii", errors="replace").rstrip("\r\n")
            out.append(text)
            if len(text) >= 4 and text[3] == " ":
                # final line
                break
        if not out or not out[-1].startswith("250"):
            raise TorControlError(f"Tor refused command '{line.split()[0]}': {out[-1] if out else 'no reply'}")
        return out

    async def protocol_info(self) -> TorInfo:
        lines = await self._cmd("PROTOCOLINFO 1")
        methods: list[str] = []
        cookie: Optional[str] = None
        ver = "?"
        for ln in lines:
            if "AUTH METHODS=" in ln:
                tail = ln.split("AUTH METHODS=", 1)[1]
                method_part = tail.split(" ", 1)[0]
                methods = method_part.split(",")
                if "COOKIEFILE=" in tail:
                    cf = tail.split('COOKIEFILE="', 1)[1].split('"', 1)[0]
                    cookie = cf
            if "Tor=" in ln:
                ver = ln.split('Tor="', 1)[1].split('"', 1)[0] if 'Tor="' in ln else ver
        return TorInfo(auth_methods=methods, cookie_file=cookie, version=ver)

    async def authenticate(self, info: TorInfo) -> None:
        methods = info.auth_methods or []

        # 1) null auth
        if "NULL" in methods:
            await self._cmd("AUTHENTICATE")
            return

        # 2) cookie / safe-cookie
        cookie_bytes: Optional[bytes] = None
        candidate_paths = [info.cookie_file] if info.cookie_file else []
        candidate_paths += [p for p in COOKIE_PATHS if p not in candidate_paths]
        for path in candidate_paths:
            if not path:
                continue
            try:
                with open(path, "rb") as f:
                    cookie_bytes = f.read()
                if cookie_bytes:
                    break
            except (OSError, PermissionError):
                continue

        if cookie_bytes is not None:
            if "SAFECOOKIE" in methods:
                await self._safecookie_auth(cookie_bytes)
                return
            if "COOKIE" in methods:
                await self._cmd("AUTHENTICATE " + binascii.hexlify(cookie_bytes).decode("ascii"))
                return

        # 3) password -- we can't help here without a known password.
        if "HASHEDPASSWORD" in methods:
            raise TorControlError(
                "Tor requires a control-port password. Either:\n"
                "  * configure 'CookieAuthentication 1' in torrc, OR\n"
                "  * set VOID_TOR_PASSWORD and modify make-invite to send it"
            )

        raise TorControlError(
            f"Could not authenticate to Tor. Methods offered: {methods}. "
            "If you see SAFECOOKIE / COOKIE, the issue is file permissions on the "
            "auth cookie -- add yourself to the 'debian-tor' (or equivalent) group, "
            "or set 'CookieAuthFileGroupReadable 1' in torrc."
        )

    async def _safecookie_auth(self, cookie: bytes) -> None:
        client_nonce = secrets.token_bytes(32)
        reply = await self._cmd("AUTHCHALLENGE SAFECOOKIE " + binascii.hexlify(client_nonce).decode("ascii"))
        # parse:  250 AUTHCHALLENGE SERVERHASH=... SERVERNONCE=...
        first = reply[-1]
        parts = first.split()
        kv = {}
        for p in parts:
            if "=" in p:
                k, v = p.split("=", 1)
                kv[k] = v
        try:
            server_hash = binascii.unhexlify(kv["SERVERHASH"])
            server_nonce = binascii.unhexlify(kv["SERVERNONCE"])
        except (KeyError, binascii.Error) as e:
            raise TorControlError(f"Bad SAFECOOKIE reply: {first}") from e

        msg = cookie + client_nonce + server_nonce
        expected = hmac.new(
            b"Tor safe cookie authentication server-to-controller hash", msg, sha256
        ).digest()
        if not hmac.compare_digest(expected, server_hash):
            raise TorControlError("Tor SAFECOOKIE server hash mismatch (this Tor may be hostile?)")
        client_hash = hmac.new(
            b"Tor safe cookie authentication controller-to-server hash", msg, sha256
        ).digest()
        await self._cmd("AUTHENTICATE " + binascii.hexlify(client_hash).decode("ascii"))

    async def add_onion(self, virt_port: int, target_port: int) -> str:
        # NEW:ED25519-V3 generates a fresh v3 key; DiscardPK = Tor doesn't return
        # it to us (so we cannot save it; it dies with the control connection).
        cmd = f"ADD_ONION NEW:ED25519-V3 Flags=DiscardPK Port={virt_port},127.0.0.1:{target_port}"
        lines = await self._cmd(cmd)
        for ln in lines:
            if "ServiceID=" in ln:
                return ln.split("ServiceID=", 1)[1].strip()
        raise TorControlError("Tor did not return a ServiceID")

    async def del_onion(self, service_id: str) -> None:
        try:
            await self._cmd(f"DEL_ONION {service_id}")
        except Exception:
            pass
