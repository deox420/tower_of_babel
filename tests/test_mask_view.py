"""Headless tests for the in-chrome MASK decode/import flow.

The CLI's ``mask decode`` (parse a mask:// URL) and ``mask import``
(decrypt an exported blob) are now reachable from the interactive
view. These drive the view through Textual's test pilot and assert an
identity is adopted, and that a wrong passphrase is rejected without
clobbering state.

Run with::

    python -m unittest tests.test_mask_view -v
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from textual.app import App, ComposeResult
    from textual.widgets import Button, Input

    from tools.mask.alias import AliasSpec
    from tools.mask.app import MaskView
    from tools.mask.avatar import generate_avatar
    from tools.mask.bundle import Identity, export_blob, passphrase_as_secure
    from tools.mask.link import build as mask_build
    _HAVE = True
    _ERR = ""
except Exception as e:  # pragma: no cover
    _HAVE = False
    _ERR = repr(e)


def _make_identity() -> "Identity":
    alias = AliasSpec(given="Elena", family="Cortes", handle="elena_cortes",
                      locale="es", profile="default")
    return Identity(alias=alias, bio="de provincias.",
                    avatar=generate_avatar(b"elena_cortes"), mail=None)


if _HAVE:
    class _Host(App):
        def compose(self) -> ComposeResult:
            yield MaskView()


@unittest.skipUnless(_HAVE, f"mask/textual unavailable: {_ERR}")
class MaskDecodeImportTests(unittest.IsolatedAsyncioTestCase):
    async def test_decode_button_reveals_input_and_decodes(self) -> None:
        app = _Host()
        async with app.run_test(size=(120, 50)) as pilot:
            view = app.query_one(MaskView)
            await pilot.pause()

            decode_input = view.query_one("#mask-decode-url", Input)
            self.assertFalse(decode_input.display)
            view.query_one("#mask-decode-btn", Button).press()
            await pilot.pause()
            self.assertTrue(decode_input.display)

            url = mask_build(_make_identity())
            view._decode_url(url)
            await pilot.pause()
            self.assertIsNotNone(view.identity)
            self.assertEqual(view.identity.alias.handle, "elena_cortes")
            # input hidden again after a successful decode
            self.assertFalse(decode_input.display)

    async def test_import_blob_round_trip(self) -> None:
        ident = _make_identity()
        with passphrase_as_secure(b"open sesame") as pw:
            blob = export_blob(ident, pw)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "id.blob"
            path.write_bytes(blob)

            app = _Host()
            async with app.run_test(size=(120, 50)) as pilot:
                view = app.query_one(MaskView)
                await pilot.pause()
                view.query_one("#mask-import-btn", Button).press()
                await pilot.pause()
                view.query_one("#mask-import-path", Input).value = str(path)
                view.query_one("#mask-import-pass", Input).value = "open sesame"
                view._import_blob_file()
                await pilot.pause()
                self.assertIsNotNone(view.identity)
                self.assertEqual(view.identity.alias.handle, "elena_cortes")
                # passphrase scrubbed from the widget
                self.assertEqual(view.query_one("#mask-import-pass", Input).value, "")

    async def test_import_wrong_passphrase_rejected(self) -> None:
        ident = _make_identity()
        with passphrase_as_secure(b"right one") as pw:
            blob = export_blob(ident, pw)
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "id.blob"
            path.write_bytes(blob)

            app = _Host()
            async with app.run_test(size=(120, 50)) as pilot:
                view = app.query_one(MaskView)
                await pilot.pause()
                view.query_one("#mask-import-path", Input).value = str(path)
                view.query_one("#mask-import-pass", Input).value = "WRONG"
                view._import_blob_file()
                await pilot.pause()
                self.assertIsNone(view.identity)


if __name__ == "__main__":
    unittest.main()
