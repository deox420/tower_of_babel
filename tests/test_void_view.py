"""Headless UI test for the in-chrome VOID view.

Drives the stage machine (lobby -> connecting -> chat -> lobby) through
Textual's test pilot and asserts each stage mounts and that a delivered
message renders in the chat log. The network/crypto path is covered
separately by ``tests.test_void_session``; this test exercises the
in-chrome rendering wiring with no server involved.

Run with::

    python -m unittest tests.test_void_view -v
"""
from __future__ import annotations

import unittest
from datetime import datetime

try:
    from textual.app import App, ComposeResult

    from tools.void.client.chrome_view import (
        VoidView,
        _ChatStage,
        _ConnectingStage,
        _LobbyStage,
    )
    _HAVE = True
    _ERR = ""
except Exception as e:  # pragma: no cover
    _HAVE = False
    _ERR = repr(e)


if _HAVE:
    class _Host(App):
        def compose(self) -> ComposeResult:
            yield VoidView()


@unittest.skipUnless(_HAVE, f"void/textual unavailable: {_ERR}")
class VoidViewStageTests(unittest.IsolatedAsyncioTestCase):
    async def test_stage_machine_and_message_render(self) -> None:
        from textual.widgets import Button

        app = _Host()
        async with app.run_test(size=(120, 50)) as pilot:
            view = app.query_one(VoidView)

            # Starts in the lobby.
            await pilot.pause()
            self.assertEqual(len(view.query(_LobbyStage)), 1)
            self.assertEqual(view.status_line(), "lobby")

            # Transport toggle flips ONION <-> CLEARNET.
            self.assertFalse(view.session.clearnet)
            view.query_one("#void-transport-toggle", Button).press()
            await pilot.pause()
            self.assertTrue(view.session.clearnet)

            # Connecting stage.
            view.on_connecting_start()
            await pilot.pause()
            self.assertEqual(len(view.query(_ConnectingStage)), 1)
            view.on_connecting_step(2)        # must not raise

            # Enter chat.
            view.on_enter_chat("the-room")
            await pilot.pause()
            self.assertEqual(len(view.query(_ChatStage)), 1)
            self.assertEqual(len(view.query(_ConnectingStage)), 0)

            # A delivered message renders in the chat log model.
            view.on_message(datetime.now(), "abcdef12", "hello in-chrome",
                            is_self=False, trusted=False)
            await pilot.pause()
            chat = view.query_one(_ChatStage)
            texts = [e.text_buf.decode() for e in chat._lines
                     if e.kind == "msg" and e.text_buf]
            self.assertIn("hello in-chrome", texts)

            # Return to lobby on disconnect.
            view.on_return_to_lobby("// disconnected (test)")
            await pilot.pause()
            self.assertEqual(len(view.query(_LobbyStage)), 1)
            self.assertEqual(len(view.query(_ChatStage)), 0)


if __name__ == "__main__":
    unittest.main()
