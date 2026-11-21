"""G3-W isolated lab fixture tests: no Docker, no ffmpeg, no live files."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "lab" / "pvr_g3w" / "prepare.py"
spec = importlib.util.spec_from_file_location("pvr_g3w_prepare", SRC)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class LabFixtureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "g3w"
        self.root.mkdir()
        self.runtime = self.root / "runtime"
        self.patchers = [
            patch.object(M, "ROOT", self.root),
            patch.object(M, "RUNTIME", self.runtime),
            patch.object(M, "GUARD", self.runtime / ".g3w-synthetic-lab"),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_before_is_two_channels_with_real_linebreaks(self):
        result = M._playlist("before")
        self.assertTrue(result.startswith("#EXTM3U\n#EXTINF"))
        self.assertEqual(result.count("#EXTINF"), 2)
        self.assertNotIn("G3W Synthetic 3", result)

    def test_added_is_three(self):
        result = M._playlist("added")
        self.assertEqual(result.count("#EXTINF"), 3)
        self.assertIn("G3W Synthetic 3", result)

    def test_removed_returns_two(self):
        self.assertEqual(M._playlist("before"), M._playlist("removed"))

    def test_init_creates_only_lab_dirs(self):
        M._preflight()
        self.assertEqual(M.GUARD.read_text(), "masqelec-g3w-synthetic-v1\n")
        self.assertTrue((self.runtime / "playlist").is_dir())

    def test_guard_mismatch_blocks(self):
        M._preflight()
        M.GUARD.write_text("not ours")
        with self.assertRaisesRegex(RuntimeError, "INVALID_LAB_MARKER"):
            M._preflight()

    def test_playlist_symlink_blocks(self):
        M._preflight()
        dest = self.runtime / "playlist" / "playlist.m3u"
        target = self.runtime / "outside"
        target.write_text("private")
        dest.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "PLAYLIST_SYMLINK_DENIED"):
            M._write_atomic(dest, M._playlist("before"))
        self.assertEqual(target.read_text(), "private")

    def test_stages_install_only_fixture(self):
        with patch.object(M, "prepare_streams", return_value=3):
            M.run("before")
        first = (self.runtime / "playlist" / "playlist.m3u")
        self.assertEqual(first.read_text().count("#EXTINF"), 2)
        for n in range(1, 4):
            (self.runtime / "streams" / ("ch%d.ts" % n)).write_bytes(b"test")
        M.run("added")
        self.assertEqual(first.read_text().count("#EXTINF"), 3)
        M.run("removed")
        self.assertEqual(first.read_text().count("#EXTINF"), 2)

    def test_add_stage_requires_prepared_streams(self):
        with self.assertRaisesRegex(RuntimeError, "LAB_STREAMS_NOT_PREPARED"):
            M.run("added")

    def test_invalid_stage_blocks(self):
        with self.assertRaisesRegex(RuntimeError, "INVALID_STAGE"):
            M.run("production")

    def test_runtime_symlink_blocks(self):
        elsewhere = self.root / "other"
        elsewhere.mkdir()
        self.runtime.symlink_to(elsewhere)
        with self.assertRaisesRegex(RuntimeError, "SYMLINK_DIRECTORY_DENIED"):
            M._preflight()


if __name__ == "__main__":
    unittest.main()
