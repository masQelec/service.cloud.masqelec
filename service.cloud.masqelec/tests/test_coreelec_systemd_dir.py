# -*- coding: utf-8 -*-
"""CoreELEC persistent unit directory: creation and legacy compatibility."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import coreelec_systemd_dir as systemd_dir


class CoreelecSystemdDirectoryTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.path = self.root / "system.d"

    def test_creates_0755_under_umask_0002(self):
        old = os.umask(0o002)
        try:
            self.assertTrue(systemd_dir.ensure_directory(str(self.path)))
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o755)

    def test_existing_0755_not_modified(self):
        self.path.mkdir()
        self.path.chmod(0o755)
        self.assertFalse(systemd_dir.ensure_directory(str(self.path)))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o755)

    def test_existing_legacy_0775_not_silently_modified(self):
        self.path.mkdir()
        self.path.chmod(0o775)
        self.assertFalse(systemd_dir.ensure_directory(str(self.path)))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o775)

    def test_symlink_denied(self):
        self.path.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            systemd_dir.ensure_directory(str(self.path))

    def test_regular_file_denied(self):
        self.path.write_text("not a directory")
        with self.assertRaises(ValueError):
            systemd_dir.ensure_directory(str(self.path))


if __name__ == "__main__":
    unittest.main()
