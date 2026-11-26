import gzip
import tempfile
import unittest
import zlib

from pathlib import Path
from unittest.mock import Mock, patch

from lib import pvr_playlist as pvr


BASE = (
    "https://raw.githubusercontent.com/"
    "masQelec/cloud.masqelec/21"
)

TEMPLATE = (
    '#EXTM3U\n'
    '#EXTINF:-1 CUID="242" tvg-chno="1",Channel A\n'
    'http://example.org/live/USER_CODE/PASS_CODE/1.ts\n'
    '#EXTINF:-1 CUID="243" tvg-chno="2",Channel B\n'
    'http://example.org/live/USER_CODE/PASS_CODE/2.ts\n'
)


class PlaylistTests(unittest.TestCase):

    def setUp(self):

        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)

        self.root = Path(folder.name)

        self.playlist = self.root / "playlist.m3u"
        self.credentials = self.root / "user"

        self.credentials.write_text(
            'USER_CODE="test-user"\n'
            'PASS_CODE="test-pass"\n'
        )

        self.fetch = Mock(return_value=TEMPLATE)

    def update(self):

        return pvr.update(
            BASE,
            playlist=self.playlist,
            credentials=self.credentials,
            fetch=self.fetch,
        )

    def test_first_install(self):

        result = self.update()

        self.assertEqual(
            result,
            {"status": "UPDATED", "channels": 2},
        )

        text = self.playlist.read_text()

        self.assertIn('CUID="242"', text)
        self.assertIn('CUID="243"', text)

        self.assertIn(
            "/test-user/test-pass/1.ts",
            text,
        )

        self.assertNotIn("USER_CODE", text)

        self.assertEqual(
            self.playlist.stat().st_mode & 0o777,
            0o600,
        )

    def test_identical_playlist_not_rewritten(self):

        self.update()

        before = self.playlist.stat()

        self.assertEqual(
            self.update()["status"],
            "UNCHANGED",
        )

        after = self.playlist.stat()

        self.assertEqual(before.st_ino, after.st_ino)
        self.assertEqual(before.st_mtime_ns, after.st_mtime_ns)

    def test_order_preserved(self):

        self.update()

        text = self.playlist.read_text()

        self.assertLess(
            text.index('CUID="242"'),
            text.index('CUID="243"'),
        )

    def test_duplicate_cuid_rejected(self):

        self.fetch.return_value = TEMPLATE.replace(
            'CUID="243"', 'CUID="242"'
        )

        with self.assertRaisesRegex(
            pvr.PlaylistError,
            "DUPLICATE_CUID",
        ):
            self.update()

        self.assertFalse(self.playlist.exists())

    def test_missing_cuid_rejected(self):

        self.fetch.return_value = TEMPLATE.replace(
            'CUID="242"', ""
        )

        with self.assertRaises(pvr.PlaylistError):
            self.update()

    def test_empty_playlist_rejected(self):

        self.fetch.return_value = "#EXTM3U\n"

        with self.assertRaises(pvr.PlaylistError):
            self.update()

    def test_html_rejected(self):

        self.fetch.return_value = "<html>Error</html>"

        with self.assertRaises(pvr.PlaylistError):
            self.update()

    def test_truncated_playlist_rejected(self):

        self.fetch.return_value = (
            TEMPLATE.rsplit("\n", 2)[0] + "\n"
        )

        with self.assertRaises(pvr.PlaylistError):
            self.update()

    def test_missing_credentials_no_download(self):

        self.credentials.unlink()

        with self.assertRaisesRegex(
            pvr.PlaylistError,
            "CREDENTIALS_MISSING",
        ):
            self.update()

        self.fetch.assert_not_called()

    def test_invalid_credentials_no_download(self):

        self.credentials.write_text(
            'USER_CODE="test"\n'
        )

        with self.assertRaises(pvr.PlaylistError):
            self.update()

        self.fetch.assert_not_called()

    def test_download_failure_preserves_playlist(self):

        self.update()

        original = self.playlist.read_bytes()

        self.fetch.side_effect = OSError("network error")

        with self.assertRaises(OSError):
            self.update()

        self.assertEqual(
            self.playlist.read_bytes(),
            original,
        )

    def test_invalid_template_preserves_playlist(self):

        self.update()

        original = self.playlist.read_bytes()

        self.fetch.return_value = "#EXTM3U\n"

        with self.assertRaises(pvr.PlaylistError):
            self.update()

        self.assertEqual(
            self.playlist.read_bytes(),
            original,
        )

    def test_atomic_failure_preserves_playlist(self):

        self.update()

        original = self.playlist.read_bytes()

        self.fetch.return_value = TEMPLATE.replace(
            "Channel B", "Channel C"
        )

        with patch.object(
            pvr.os,
            "replace",
            side_effect=OSError("disk error"),
        ):

            with self.assertRaises(OSError):
                self.update()

        self.assertEqual(
            self.playlist.read_bytes(),
            original,
        )

        self.assertEqual(
            list(self.root.glob(".playlist-*")),
            [],
        )

    def test_channel_removal_valid(self):

        self.update()

        self.fetch.return_value = (
            "\n".join(TEMPLATE.splitlines()[:3]) + "\n"
        )

        self.assertEqual(
            self.update(),
            {"status": "UPDATED", "channels": 1},
        )

    def test_channel_addition_valid(self):

        self.update()

        self.fetch.return_value += (
            '#EXTINF:-1 CUID="244",Channel C\n'
            'http://example.org/live/USER_CODE/PASS_CODE/3.ts\n'
        )

        self.assertEqual(
            self.update()["channels"],
            3,
        )

    def test_gzip(self):

        self.assertEqual(
            pvr.decode_response(
                gzip.compress(TEMPLATE.encode()),
                "gzip",
            ),
            TEMPLATE,
        )

    def test_deflate(self):

        self.assertEqual(
            pvr.decode_response(
                zlib.compress(TEMPLATE.encode()),
                "deflate",
            ),
            TEMPLATE,
        )

    def test_newline_normalization(self):

        self.assertEqual(
            pvr.normalize(
                TEMPLATE.replace("\n", "\r\n").encode()
            ),
            TEMPLATE,
        )


if __name__ == "__main__":
    unittest.main()
