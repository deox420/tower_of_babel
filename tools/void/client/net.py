"""Thin async WS wrapper for the client. Supports SOCKS5 (Tor) tunneling."""
from __future__ import annotations

import asyncio
import json
import ssl
from typing import Any, Callable, Awaitable
from urllib.parse import urlparse

import websockets
from websockets.client import WebSocketClientProtocol


class Net:
    def __init__(
        self,
        url: str,
        insecure: bool = False,
        proxy_url: str | None = None,
    ) -> None:
        self.url = url
        self.insecure = insecure
        self.proxy_url = proxy_url  # e.g. "socks5://127.0.0.1:9050"
        self.ws: WebSocketClientProtocol | None = None
        self._reader: asyncio.Task | None = None
        self._on_message: Callable[[dict], Awaitable[None]] | None = None
        self._on_close: Callable[[str], Awaitable[None]] | None = None

    async def connect(self) -> None:
        ssl_ctx: ssl.SSLContext | None = None
        if self.url.startswith("wss://"):
            ssl_ctx = ssl.create_default_context()
            if self.insecure:
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE

        common_kwargs = dict(
            max_size=16 * 1024,
            ping_interval=20,
            ping_timeout=20,
            compression=None,
            open_timeout=20,
        )

        if self.proxy_url:
            from python_socks.async_.asyncio import Proxy
            parsed = urlparse(self.url)
            host = parsed.hostname or ""
            port = parsed.port or (443 if parsed.scheme == "wss" else 80)
            proxy = Proxy.from_url(self.proxy_url)
            sock = await proxy.connect(dest_host=host, dest_port=port, timeout=20)
            # When tunneling through SOCKS5 we need server_hostname for SNI/TLS.
            self.ws = await websockets.connect(
                self.url,
                sock=sock,
                ssl=ssl_ctx,
                server_hostname=host if ssl_ctx else None,
                **common_kwargs,
            )
        else:
            self.ws = await websockets.connect(
                self.url,
                ssl=ssl_ctx,
                **common_kwargs,
            )

    def start_reader(
        self,
        on_message: Callable[[dict], Awaitable[None]],
        on_close: Callable[[str], Awaitable[None]],
    ) -> None:
        self._on_message = on_message
        self._on_close = on_close
        self._reader = asyncio.create_task(self._read_loop())

    async def _read_loop(self) -> None:
        reason = "closed"
        try:
            assert self.ws is not None
            async for raw in self.ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if isinstance(data, dict) and self._on_message:
                    try:
                        await self._on_message(data)
                    except Exception:
                        pass
        except websockets.ConnectionClosed as e:
            reason = f"closed {e.code}"
        except Exception as e:
            reason = f"error {type(e).__name__}"
        finally:
            if self._on_close:
                try:
                    await self._on_close(reason)
                except Exception:
                    pass

    async def send(self, obj: dict[str, Any]) -> None:
        if self.ws is None:
            return
        try:
            await self.ws.send(json.dumps(obj, separators=(",", ":")))
        except Exception:
            pass

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
            self._reader = None
        if self.ws is not None:
            try:
                await self.ws.close()
            except Exception:
                pass
            self.ws = None
