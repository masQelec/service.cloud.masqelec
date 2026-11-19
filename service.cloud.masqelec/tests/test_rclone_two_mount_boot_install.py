# -*- coding: utf-8 -*-
"""Optional boot recovery systemd installation never blocks Kodi."""
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_boot_install as installer


class BootInstallerTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root = Path(t.name)
        self.units = self.root / "system.d"
        self.units.mkdir(mode=0o700)
        self.units.chmod(0o755)
        self.script = self.root / "early.py"
        self.script.write_text("# fixture\n")
        self.actions = []
        self.adapter = SimpleNamespace(
            enabled=True, unit_dir=str(self.units),
            _systemctl=lambda *a: self.actions.append(a))

    def install(self, **changes):
        with mock.patch.object(installer, "ADDON_SCRIPT", str(self.script)), \
             mock.patch.object(installer, "_is_root", return_value=True):
            return installer.ensure_installed(
                self.adapter, authorized=True,
                verify=lambda name: name == installer.UNIT_NAME, **changes)

    def test_installs_optional_wants_after(self):
        self.assertEqual(self.install(), "READY")
        unit = (self.units / installer.UNIT_NAME).read_bytes()
        drop = (self.units / "kodi.service.d" / installer.DROPIN_NAME)
        self.assertEqual(drop.read_bytes(), installer.DROPIN)
        self.assertIn(b"Before=kodi.service", unit)
        self.assertIn(b"TimeoutStartSec=45", unit)
        self.assertIn(b"Wants=masqelec-v2-recovery.service", drop.read_bytes())
        self.assertNotIn(b"Requires=", drop.read_bytes())
        self.assertEqual(stat.S_IMODE(drop.stat().st_mode), 0o644)
        self.assertEqual(self.actions, [("daemon-reload",)])

    def test_second_install_idempotent(self):
        self.assertEqual(self.install(), "READY")
        old = (self.units / installer.UNIT_NAME).stat().st_ino
        self.assertEqual(self.install(), "READY")
        self.assertEqual((self.units / installer.UNIT_NAME).stat().st_ino, old)

    def test_existing_operator_dropin_blocks_before_mutation(self):
        drop = self.units / "kodi.service.d"
        drop.mkdir()
        (drop / installer.DROPIN_NAME).write_text("custom")
        self.assertEqual(self.install(), "BLOCKED_BOOT_INSTALL_CONFLICT")
        self.assertFalse((self.units / installer.UNIT_NAME).exists())

    def test_unverified_ordering_blocks_cutover(self):
        with mock.patch.object(installer, "ADDON_SCRIPT", str(self.script)), \
             mock.patch.object(installer.os, "geteuid", return_value=os.geteuid()):
            self.assertEqual(installer.ensure_installed(
                self.adapter, authorized=True, verify=lambda _: False),
                "BLOCKED_BOOT_INSTALL_UNVERIFIED")

    def test_unapproved_cannot_write(self):
        self.assertEqual(installer.ensure_installed(self.adapter),
                         "BLOCKED_BOOT_INSTALL_NOT_AUTHORIZED")
        self.assertEqual(list(self.units.iterdir()), [])

    def test_symlink_dropin_folder_denied(self):
        (self.units / "kodi.service.d").symlink_to(self.root)
        self.assertEqual(self.install(), "BLOCKED_BOOT_INSTALL_FAILED")
        self.assertFalse((self.units / installer.UNIT_NAME).exists())

    def test_dependency_parser_rejects_missing_after(self):
        class Result:
            returncode = 0
            stdout = b"Wants=masqelec-v2-recovery.service\nAfter=kodi.target\n"
        with mock.patch.object(installer.subprocess, "run", return_value=Result()):
            self.assertFalse(installer.verify_dependency(installer.UNIT_NAME))

    def test_dependency_parser_accepts_wants_and_after(self):
        class Result:
            returncode = 0
            stdout = (b"Wants=other.service masqelec-v2-recovery.service\n"
                      b"After=local-fs.target masqelec-v2-recovery.service\n")
        with mock.patch.object(installer.subprocess, "run", return_value=Result()):
            self.assertTrue(installer.verify_dependency(installer.UNIT_NAME))


if __name__ == "__main__":
    unittest.main()
