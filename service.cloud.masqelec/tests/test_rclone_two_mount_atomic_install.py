# -*- coding: utf-8 -*-
"""Ficheros de transacción: instalación exclusive fail-closed con /tmp."""
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_atomic_install as install


class ExclusiveInstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "private"
        self.root.mkdir(mode=0o700)
        self.path = self.root / "account1.conf"

    def test_private_config_created_0600(self):
        install.install_exclusive(str(self.path), b"synthetic", 0o600)
        self.assertEqual(self.path.read_bytes(), b"synthetic")
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_unit_mode_0644(self):
        name = self.root / "rclone_library_1.service"
        install.install_exclusive(str(name), b"[Unit]\nA=B", 0o644)
        self.assertEqual(stat.S_IMODE(name.stat().st_mode), 0o644)

    def test_never_overwrites_existing_config(self):
        self.path.write_bytes(b"keep-original")
        with self.assertRaises(FileExistsError):
            install.install_exclusive(str(self.path), b"new-secret", 0o600)
        self.assertEqual(self.path.read_bytes(), b"keep-original")

    def test_never_overwrites_symlink(self):
        original = self.root / "real"
        original.write_bytes(b"keep-original")
        self.path.symlink_to(original)
        with self.assertRaises(FileExistsError):
            install.install_exclusive(str(self.path), b"new-secret", 0o600)
        self.assertEqual(original.read_bytes(), b"keep-original")

    def test_rejects_world_writable_parent(self):
        self.root.chmod(0o777)
        with self.assertRaises(ValueError):
            install.install_exclusive(str(self.path), b"secret", 0o600)

    def test_rejects_symlink_parent(self):
        alias = Path(self.tmp.name) / "alias"
        alias.symlink_to(self.root)
        with self.assertRaises(ValueError):
            install.install_exclusive(str(alias / "account2.conf"),
                                      b"secret", 0o600)

    def test_rejects_missing_parent(self):
        with self.assertRaises(OSError):
            install.install_exclusive(
                str(self.root / "missing" / "conf"), b"secret", 0o600)

    def test_rejects_secret_modes_other_than_0600_or_0644(self):
        for mode in (0o777, 0o666, 0o400, 0o000):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                install.install_exclusive(str(self.path), b"secret", mode)

    def test_rejects_empty_or_non_bytes(self):
        for bad in (b"", "", None):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                install.install_exclusive(str(self.path), bad, 0o600)

    def test_rejects_overly_large(self):
        with self.assertRaises(ValueError):
            install.install_exclusive(str(self.path),
                                      b"a" * (1024 * 1024 + 1), 0o600)

    def test_remove_identical_own_file(self):
        install.install_exclusive(str(self.path), b"synthetic", 0o600)
        self.assertTrue(install.remove_if_identical(
            str(self.path), b"synthetic"))
        self.assertFalse(self.path.exists())

    def test_remove_mismatched_does_not_touch(self):
        install.install_exclusive(str(self.path), b"original", 0o600)
        with self.assertRaises(ValueError):
            install.remove_if_identical(str(self.path), b"replacement")
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_remove_symlink_rejected(self):
        other = self.root / "other"
        other.write_bytes(b"secret")
        self.path.symlink_to(other)
        with self.assertRaises(ValueError):
            install.remove_if_identical(str(self.path), b"secret")
        self.assertEqual(other.read_bytes(), b"secret")

    def test_atomic_non_overwrite_on_race(self):
        def conflict(tmp, dest, **kwargs):
            self.path.write_bytes(b"competing-process")
            raise FileExistsError("race")
        with mock.patch.object(install.os, "link", side_effect=conflict):
            with self.assertRaises(FileExistsError):
                install.install_exclusive(str(self.path),
                                          b"original", 0o600)
        self.assertEqual(self.path.read_bytes(), b"competing-process")

    def test_no_systemd_or_network_ops_in_installer(self):
        src = (Path(__file__).resolve().parents[1] /
               "lib/rclone_two_mount_atomic_install.py").read_text()
        self.assertNotIn("import subprocess", src)
        self.assertNotIn("urllib", src)
        self.assertNotIn("systemctl start", src)


if __name__ == "__main__":
    unittest.main()
