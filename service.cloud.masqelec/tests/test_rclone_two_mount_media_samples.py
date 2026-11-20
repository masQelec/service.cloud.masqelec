# -*- coding: utf-8 -*-
"""Muestras de media de dos cuentas desde catalog .strm, sin red/Kodi."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_media_samples as samples


class LocalStrmDiscoveryTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        base = Path(temp.name)
        self.movies = base / "videos"
        self.tvshows = base / "tvshows"
        self.movies.mkdir()
        self.tvshows.mkdir()
        self.roots = (str(self.movies), str(self.tvshows))

    def strm(self, parent, name, value):
        path = parent / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
        return path

    def test_picks_one_local_strm_per_account(self):
        a = b"/storage/.mnt/videos/1/Film 2026.mkv\n"
        b = b"/storage/.mnt/tvshows/2/Serie/Season 02/episode.avi\n"
        self.strm(self.movies, "film.strm", a)
        self.strm(self.tvshows, "Serie/Season 02/episode.strm", b)
        self.assertEqual(samples.discover(self.roots),
                         (a.rstrip(b"\n").decode(), b.rstrip(b"\n").decode()))

    def test_accepts_both_samples_within_same_local_catalog(self):
        a = self.strm(self.movies, "a.strm",
                      b"/storage/.mnt/videos/1/a.mkv\n")
        b = self.strm(self.movies, "b.strm",
                      b"/storage/.mnt/videos/2/b.mkv\n")
        self.assertEqual(samples.discover(self.roots), (
            "/storage/.mnt/videos/1/a.mkv",
            "/storage/.mnt/videos/2/b.mkv"))

    def test_no_remote_or_unknown_account_returns_none(self):
        self.strm(self.movies, "one.strm",
                  b"/storage/.mnt/videos/1/a.mkv\n")
        self.strm(self.movies, "remote.strm",
                  b"https://example.invalid/remote/video.mkv\n")
        self.assertIsNone(samples.discover(self.roots))

    def test_rejects_traversal_double_slashes_and_controls(self):
        for value in (
            b"/storage/.mnt/videos/1/../2/evil.mkv",
            b"/storage/.mnt/videos/1//other.mkv",
            b"/storage/.mnt/videos/1/video.mkv\nother",
            b"/storage/.mnt/videos/1/video.mkv\0",
            b"/storage/.mnt/videos/1/",
            b"/storage/.mnt/videos/10/evil.mkv",
            b"/storage/.mnt/videos/1/video.mkv\rBAD",
            b"plugin://something\n",
            b"\xff",
        ):
            with self.subTest(value=value):
                self.assertIsNone(samples._media_account(value))

    def test_no_symlink_strm_or_symlink_directory_read(self):
        external = self.strm(self.movies, "target.strm",
                             b"/storage/.mnt/videos/1/a.mkv\n")
        (self.tvshows / "fake.strm").symlink_to(external)
        (self.tvshows / "linkdir").symlink_to(self.movies, target_is_directory=True)
        self.assertIsNone(samples.discover(self.roots))
        self.strm(self.tvshows, "real.strm",
                  b"/storage/.mnt/videos/2/b.mkv\n")
        self.assertIsNotNone(samples.discover(self.roots))

    def test_symlink_catalog_root_denied(self):
        link = self.tvshows.parent / "linkroot"
        link.symlink_to(self.tvshows, target_is_directory=True)
        self.assertIsNone(samples.discover((str(link),)))

    def test_too_large_strm_not_read(self):
        self.strm(self.movies, "large.strm",
                  b"x" * (samples.MAX_STRM_BYTES + 1))
        self.assertIsNone(samples.discover(self.roots))

    def test_oversize_scan_refuses_before_second_account(self):
        self.strm(self.movies, "a.strm",
                  b"/storage/.mnt/videos/1/a.mkv\n")
        self.strm(self.tvshows, "b.strm",
                  b"/storage/.mnt/videos/2/b.mkv\n")
        self.assertIsNone(samples.discover(self.roots, max_files=1))

    def test_malformed_catalog_and_missing_root_blocks(self):
        self.assertIsNone(samples.discover((str(self.movies),
                                            str(self.movies / "missing"))))
        self.assertIsNone(samples.discover((None,)))
        self.assertIsNone(samples.discover(roots=()))

    def test_os_errors_fail_closed(self):
        with mock.patch.object(samples.os, "scandir",
                               side_effect=PermissionError("blocked")):
            self.assertIsNone(samples.discover(self.roots))

    def test_media_account_parser_does_not_accept_bytes_wrong_type(self):
        for raw in ("str", None, b"", b"x" * 9000):
            with self.subTest(value=type(raw).__name__):
                self.assertIsNone(samples._media_account(raw))

    def test_inventory_cli_only_reports_presence_not_media_paths(self):
        from unittest import mock
        from contextlib import redirect_stdout
        from io import StringIO
        with mock.patch.object(
                samples, "discover",
                return_value=("/storage/.mnt/videos/1/SECRET-FILM.mkv",
                              "/storage/.mnt/videos/2/SECRET-SERIES.mkv")), \
             redirect_stdout(StringIO()) as output:
            code = samples.main(["--inventory"])
        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("MEDIA_DISCOVERY_RESULT=PASS_2_LOCAL_STRM_ACCOUNTS", text)
        self.assertNotIn("SECRET-FILM", text)
        self.assertNotIn("SECRET-SERIES", text)
        self.assertIn("OAUTH_CONFIG_READ=NO", text)

    def test_invalid_cli_does_not_scan(self):
        from unittest import mock
        from contextlib import redirect_stdout
        from io import StringIO
        with mock.patch.object(samples, "discover",
                               side_effect=AssertionError("no scan")), \
             redirect_stdout(StringIO()) as output:
            self.assertEqual(samples.main(["--migrate"]), 2)
        self.assertEqual(output.getvalue().strip(),
                         "MEDIA_DISCOVERY_RESULT=BLOCKED_INVALID_MODE")

    def test_inventory_cli_missing_account_reports_block(self):
        from unittest import mock
        from contextlib import redirect_stdout
        from io import StringIO
        with mock.patch.object(samples, "discover", return_value=None), \
             redirect_stdout(StringIO()) as output:
            self.assertEqual(samples.main(["--inventory"]), 2)
        self.assertIn("BLOCKED_NO_TWO_LOCAL_SAMPLES", output.getvalue())
        self.assertIn("REAL_OAUTH_PROBE_ALLOWED=NO", output.getvalue())

    def test_source_has_no_remote_media_reads(self):
        code = (Path(__file__).resolve().parents[1] /
                "lib/rclone_two_mount_media_samples.py").read_text()
        for forbidden in ("subprocess.run", "rclone lsf", "urllib",
                          "import socket", "systemctl",
                          "os.unlink", "os.replace"):
            self.assertNotIn(forbidden, code)


if __name__ == "__main__":
    unittest.main()
