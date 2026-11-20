# -*- coding: utf-8 -*-
"""No reboot performed: two-phase lab safety and cleanup regression."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "rclone_two_mount_reboot_journal_lab.py"
SPEC = importlib.util.spec_from_file_location("masqelec_reboot_journal_lab", SCRIPT)
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)
BOOT_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
BOOT_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class RebootJournalLabTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="masqelec-reboot-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "isolated-lab"
        patch_root = mock.patch.object(lab, "ROOT", self.root)
        patch_owner = mock.patch.object(lab, "_is_root", return_value=True)
        patch_mount = mock.patch.object(lab, "_mounts_clear", return_value=True)
        patch_boot = mock.patch.object(lab, "_boot_id", return_value=BOOT_A)
        for patch in (patch_root, patch_owner, patch_mount, patch_boot):
            patch.start()
            self.addCleanup(patch.stop)

    def test_requires_changed_real_boot_id_to_rollback(self):
        self.assertEqual(lab.prepare(), "PREPARED_REBOOT_REQUIRED")
        self.assertEqual(lab.verify(), "BLOCKED_REBOOT_NOT_OBSERVED")
        self.assertEqual((self.root / "account1.conf").read_bytes(), lab.CANDIDATE)
        with mock.patch.object(lab, "_boot_id", return_value=BOOT_B):
            self.assertEqual(lab.verify(),
                             "PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK")
        self.assertFalse(self.root.exists())

    def test_cannot_prepare_twice_or_clobber_existing_dir(self):
        self.assertEqual(lab.prepare(), "PREPARED_REBOOT_REQUIRED")
        self.assertEqual(lab.prepare(), "BLOCKED_EXISTING_LAB")
        self.assertTrue((self.root / "account1.bak").is_file())

    def test_unexpected_file_blocks_and_is_not_deleted(self):
        self.assertEqual(lab.prepare(), "PREPARED_REBOOT_REQUIRED")
        extra = self.root / "operator-data.txt"
        extra.write_text("preserve")
        with mock.patch.object(lab, "_boot_id", return_value=BOOT_B):
            with self.assertRaises(ValueError):
                lab.verify()
        self.assertEqual(extra.read_text(), "preserve")
        self.assertTrue(self.root.exists())

    def test_corrupt_candidate_blocks_without_backup_restore(self):
        self.assertEqual(lab.prepare(), "PREPARED_REBOOT_REQUIRED")
        target = self.root / "account1.conf"
        target.write_bytes(b"unexpected-candidate")
        target.chmod(0o600)
        with mock.patch.object(lab, "_boot_id", return_value=BOOT_B):
            with self.assertRaises(ValueError):
                lab.verify()
        self.assertEqual(target.read_bytes(), b"unexpected-candidate")
        self.assertEqual((self.root / "account1.bak").read_bytes(), lab.ORIGINAL)

    def test_disabled_no_io(self):
        with mock.patch.object(lab, "_is_root", return_value=False):
            self.assertEqual(lab.prepare(), "BLOCKED_NOT_ROOT")
        self.assertFalse(self.root.exists())

    def test_requires_confirmation(self):
        self.assertEqual(lab.main(["--prepare"]), 2)
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
