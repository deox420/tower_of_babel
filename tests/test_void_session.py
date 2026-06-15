"""Integration test for the VOID session controller.

Spins up the real blind-relay server in-process (clearnet, no TLS),
drives two :class:`VoidSession` instances through the X3DH + Double
Ratchet handshake, and asserts an end-to-end encrypted message is
delivered both ways. This is the automated gate for the orchestration
that both the standalone client and the in-chrome view share — the TUI
rendering is verified separately, but the wire/crypto path is covered
here.

Stdlib ``unittest`` + asyncio. Run with::

    python -m unittest tests.test_void_session -v
"""
from __future__ import annotations

import asyncio
import unittest
from datetime import datetime

try:
    from tools.void.client.session import VoidSession
    from tools.void.server import main as srv
    _HAVE_VOID = True
    _IMPORT_ERR = ""
except Exception as e:  # pragma: no cover - missing optional C ext (xeddsa)
    _HAVE_VOID = False
    _IMPORT_ERR = repr(e)


class CaptureUI:
    """Minimal VoidUI implementation that records what the session emits."""

    def __init__(self) -> None:
        self.messages: list[dict] = []
        self.systems: list[tuple[str, bool]] = []
        self.in_chat = False
        self.connecting_failed: str | None = None
        self.returned_to_lobby: str | None = None
        self.users: list[str] = []

    def on_system(self, text: str, *, error: bool = False) -> None:
        self.systems.append((text, error))

    def on_message(self, ts: datetime, fp: str, text: str, *,
                   is_self: bool, trusted: bool) -> None:
        self.messages.append({"fp": fp, "text": text, "is_self": is_self})

    def on_status_changed(self) -> None:
        pass

    def on_connecting_start(self) -> None:
        pass

    def on_connecting_step(self, idx: int) -> None:
        pass

    def on_connecting_failed(self, msg: str) -> None:
        self.connecting_failed = msg

    def on_enter_chat(self, room_display: str) -> None:
        self.in_chat = True

    def on_return_to_lobby(self, error: str | None) -> None:
        self.returned_to_lobby = error

    def on_users_changed(self, users: list[str]) -> None:
        self.users = list(users)

    def on_quit(self) -> None:
        pass


async def _wait_until(predicate, timeout: float = 10.0,
                      interval: float = 0.1) -> bool:
    loops = int(timeout / interval)
    for _ in range(loops):
        if predicate():
            return True
        await asyncio.sleep(interval)
    return predicate()


@unittest.skipUnless(_HAVE_VOID, f"VOID deps unavailable: {_IMPORT_ERR}")
class VoidSessionRoundTripTest(unittest.TestCase):
    def test_two_peers_exchange_encrypted_messages(self) -> None:
        async def run() -> None:
            port = 8791
            url = f"ws://127.0.0.1:{port}"
            srv.JITTER_ENABLED = False          # deterministic + fast
            server_task = asyncio.ensure_future(srv._serve("127.0.0.1", port, None))
            await asyncio.sleep(0.4)
            ua, ub = CaptureUI(), CaptureUI()
            sa = VoidSession(ua, server=url, insecure=True, onion_target=None,
                             clearnet=True, socks_url="", cover_enabled=False)
            sb = VoidSession(ub, server=url, insecure=True, onion_target=None,
                             clearnet=True, socks_url="", cover_enabled=False)
            try:
                await sa.enter_room("the-room", "s3cret", url)
                await sb.enter_room("the-room", "s3cret", url)
                self.assertTrue(ua.in_chat)
                self.assertTrue(ub.in_chat)

                # Wait for at least one ratchet to come up on each side.
                ready = await _wait_until(
                    lambda: any(p.dr is not None for p in sa.peer_sessions.values())
                    and any(p.dr is not None for p in sb.peer_sessions.values()),
                    timeout=10.0,
                )
                self.assertTrue(ready, "ratchet sessions never established")

                await sa.send_message("hello from A")
                got_b = await _wait_until(
                    lambda: any(m["text"] == "hello from A" and not m["is_self"]
                                for m in ub.messages),
                    timeout=8.0,
                )
                self.assertTrue(got_b, f"B never received A's message: {ub.messages}")

                await sb.send_message("reply from B")
                got_a = await _wait_until(
                    lambda: any(m["text"] == "reply from B" and not m["is_self"]
                                for m in ua.messages),
                    timeout=8.0,
                )
                self.assertTrue(got_a, f"A never received B's reply: {ua.messages}")

                # Local echo: each side sees its own outbound message.
                self.assertTrue(any(m["is_self"] and m["text"] == "hello from A"
                                    for m in ua.messages))
            finally:
                await sa.purge(send_leave=False)
                await sb.purge(send_leave=False)
                server_task.cancel()
                try:
                    await server_task
                except asyncio.CancelledError:
                    pass

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
