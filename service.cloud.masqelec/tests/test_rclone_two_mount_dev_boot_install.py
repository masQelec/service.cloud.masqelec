# -*- coding: utf-8 -*-
"""The real-unit dev installer never touches credentials or mount units."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

P = Path(__file__).resolve().parents[1] / "tools" / "rclone_two_mount_dev_boot_install.py"
SPEC = importlib.util.spec_from_file_location("masqelec_dev_boot_cli", P)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


class DevBootInstallerTests(unittest.TestCase):
    def test_invalid_command_no_ops(self):
        with mock.patch.object(cli, "_install", side_effect=AssertionError("install called")):
            self.assertEqual(cli.main(["--install-real-boot-unit"]), 2)

    def test_off_by_default_gates(self):
        with mock.patch.object(cli, "_root", return_value=False):
            self.assertEqual(cli._preflight(), "BLOCKED_NOT_ROOT")
        with mock.patch.object(cli, "_root", return_value=True), mock.patch.object(
                cli.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", True), mock.patch.object(
                cli, "_expected_path", side_effect=AssertionError("no file access")):
            self.assertEqual(cli._preflight(), "BLOCKED_RELEASE_FLAGS_ENABLED")

    def test_install_requires_preflight(self):
        with mock.patch.object(cli, "_preflight", return_value="BLOCKED_UNSAFE_FILESYSTEM"), \
             mock.patch.object(cli.boot, "ensure_installed",
                               side_effect=AssertionError("must not install")):
            self.assertEqual(cli._install(), "BLOCKED_UNSAFE_FILESYSTEM")

    def test_only_existing_addon_tree_may_install(self):
        with mock.patch.object(cli, "_root", return_value=True), \
             mock.patch.object(cli, "_flags_off", return_value=True), \
             mock.patch.object(cli, "_expected_path", return_value=False):
            self.assertEqual(cli._preflight(), "BLOCKED_ADDON_PATH_NOT_INSTALLED")

    def test_install_calls_exact_production_installer(self):
        with mock.patch.object(cli, "_preflight", return_value="READY_DISABLED_ONLY"), \
             mock.patch.object(cli.boot, "ensure_installed", return_value="READY") as install, \
             mock.patch.object(cli.boot, "verify_dependency", return_value=True):
            self.assertEqual(cli._install(), "READY_REAL_BOOT_ORDER_INSTALLED")
            self.assertTrue(install.called)
            self.assertTrue(install.call_args.kwargs["authorized"])

    def test_remove_only_exact_owned_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "kodi.service.d").mkdir(mode=0o755)
            (folder / "kodi.service.d").chmod(0o755)
            (folder / cli.boot.UNIT_NAME).write_bytes(cli.boot.UNIT)
            (folder / "kodi.service.d" / cli.boot.DROPIN_NAME).write_bytes(
                cli.boot.DROPIN)
            with mock.patch.object(cli, "_preflight", return_value="READY_DISABLED_ONLY"), \
                 mock.patch.object(cli, "SYSTEMD", tmp), \
                 mock.patch.object(cli, "_command", return_value=True):
                self.assertEqual(cli._remove(), "REMOVED_OWN_UNIT_AND_DROPIN")
            self.assertFalse((folder / cli.boot.UNIT_NAME).exists())
            self.assertFalse((folder / "kodi.service.d" / cli.boot.DROPIN_NAME).exists())

    def test_group_writable_dropin_not_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            dropdir = folder / "kodi.service.d"
            dropdir.mkdir(mode=0o755)
            dropdir.chmod(0o775)
            (folder / cli.boot.UNIT_NAME).write_bytes(cli.boot.UNIT)
            drop = dropdir / cli.boot.DROPIN_NAME
            drop.write_bytes(cli.boot.DROPIN)
            with mock.patch.object(cli, "_preflight", return_value="READY_DISABLED_ONLY"), \\
                 mock.patch.object(cli, "SYSTEMD", tmp), \\
                 mock.patch.object(cli, "_command", return_value=True):
                self.assertEqual(cli._remove(), "BLOCKED_REMOVE_FAILED")
            self.assertTrue(drop.exists())
            self.assertTrue((folder / cli.boot.UNIT_NAME).exists())

    def test_operator_modified_dropin_never_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "kodi.service.d").mkdir(mode=0o755)
            (folder / "kodi.service.d").chmod(0o755)
            (folder / cli.boot.UNIT_NAME).write_bytes(cli.boot.UNIT)
            path = folder / "kodi.service.d" / cli.boot.DROPIN_NAME
            path.write_bytes(b"operator custom")
            with mock.patch.object(cli, "_preflight", return_value="READY_DISABLED_ONLY"), \
                 mock.patch.object(cli, "SYSTEMD", tmp):
                self.assertEqual(cli._remove(), "BLOCKED_EXISTING_DROPIN_CONFLICT")
            self.assertEqual(path.read_bytes(), b"operator custom")


if __name__ == "__main__":
    unittest.main()
