# -*- coding: utf-8 -*-
"""Journal cutover privado: fsync, bloqueo, fases y fallos sintéticos."""
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_rollout as rollout
from test_rclone_mount_isolation import wrapped_conf, sample_units


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.parent = str(Path(self.tmp.name) / "journal")
        self.conf = wrapped_conf("crypt")
        self.units = sample_units()

    def prepared(self):
        with journal.locked(self.parent):
            return journal.prepare(self.parent, self.conf, self.units)

    def test_prepare_creates_private_durable_inventory(self):
        target = self.prepared()
        self.assertEqual(journal.phase(target), "prepared")
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), 0o700)
        self.assertEqual(set(os.listdir(target)),
                         {"canonical.conf", "phase.json"} |
                         set(rollout.LEGACY_SERVICES))
        for name in os.listdir(target):
            self.assertEqual(
                stat.S_IMODE(os.stat(os.path.join(target,name)).st_mode), 0o600)
        self.assertEqual(Path(target, "canonical.conf").read_bytes(), self.conf)

    def test_prepare_never_installs_live_units(self):
        self.prepared()
        self.assertFalse(Path(self.tmp.name, "system.d").exists())
        self.assertFalse(Path(self.tmp.name, "rclone.conf").exists())

    def test_existing_transaction_not_overwritten(self):
        target = self.prepared()
        original = Path(target, "canonical.conf").read_bytes()
        with journal.locked(self.parent):
            with self.assertRaisesRegex(ValueError, "Existing journal"):
                journal.prepare(self.parent, self.conf+b"\n", self.units)
        self.assertEqual(Path(target, "canonical.conf").read_bytes(),original)

    def test_invalid_config_never_creates_journal(self):
        bad = self.conf.replace(b"type = crypt", b"type = alias")
        with journal.locked(self.parent):
            with self.assertRaises(ValueError):
                journal.prepare(self.parent, bad, self.units)
        self.assertFalse(Path(self.parent, rollout.CANDIDATE_ID).exists())

    def test_missing_unit_blocks(self):
        units = dict(self.units)
        units.pop(next(iter(units)))
        with journal.locked(self.parent):
            with self.assertRaises(ValueError):
                journal.prepare(self.parent, self.conf, units)

    def test_unsafe_parent_permissions_block(self):
        os.makedirs(self.parent, mode=0o755)
        with self.assertRaisesRegex(ValueError,"Unsafe journal directory"):
            with journal.locked(self.parent):
                pass

    def test_symlink_parent_blocks(self):
        original = Path(self.tmp.name, "real")
        original.mkdir(mode=0o700)
        os.symlink(original, self.parent)
        with self.assertRaises(ValueError):
            with journal.locked(self.parent):
                pass

    def test_journal_lock_protected_and_private(self):
        with journal.locked(self.parent):
            info = os.stat(Path(self.parent, ".lock"))
            self.assertEqual(stat.S_IMODE(info.st_mode),0o600)
            with self.assertRaises(BlockingIOError):
                with journal.locked(self.parent):
                    pass

    def test_unsafe_lock_permissions_block(self):
        with journal.locked(self.parent):
            pass
        Path(self.parent, ".lock").chmod(0o644)
        with self.assertRaises(ValueError):
            with journal.locked(self.parent):
                pass

    def test_absent_journal_safe(self):
        self.assertFalse(journal.needs_manual_recovery(self.parent))

    def test_prepared_journal_not_mutating(self):
        self.prepared()
        self.assertFalse(journal.needs_manual_recovery(self.parent))

    def test_started_requires_manual_recovery(self):
        target = self.prepared()
        with journal.locked(self.parent):
            journal.transition(target,"prepared","cutover_started")
        self.assertTrue(journal.needs_manual_recovery(self.parent))

    def test_active_requires_manual_recovery_without_operational_adapter(self):
        target = self.prepared()
        with journal.locked(self.parent):
            journal.transition(target,"prepared","cutover_started")
            journal.transition(target,"cutover_started","active")
        self.assertTrue(journal.needs_manual_recovery(self.parent))

    def test_rollback_requires_legacy_restored(self):
        target = self.prepared()
        with journal.locked(self.parent):
            journal.transition(target,"prepared","cutover_started")
            journal.transition(target,"cutover_started","rollback_required")
        self.assertTrue(journal.needs_manual_recovery(self.parent))
        with journal.locked(self.parent):
            journal.transition(target,"rollback_required","legacy_restored")
        self.assertFalse(journal.needs_manual_recovery(self.parent))

    def test_cannot_skip_stages_or_reuse(self):
        target = self.prepared()
        with journal.locked(self.parent):
            for new in ("active","rollback_required","legacy_restored",
                        "prepared"):
                with self.assertRaises(ValueError):
                    journal.transition(target,"prepared",new)

    def test_wrong_expected_phase_blocks(self):
        target = self.prepared()
        with journal.locked(self.parent):
            with self.assertRaises(ValueError):
                journal.transition(target,"cutover_started","active")

    def test_corrupt_phase_blocks(self):
        target = self.prepared()
        Path(target,"phase.json").write_text("{}")
        self.assertTrue(journal.needs_manual_recovery(self.parent))

    def test_symlink_phase_blocks(self):
        target = self.prepared()
        phase_file = Path(target,"phase.json")
        phase_file.unlink()
        phase_file.symlink_to(Path(target,"canonical.conf"))
        self.assertTrue(journal.needs_manual_recovery(self.parent))

    def test_no_secrets_in_phase_file(self):
        target = self.prepared()
        text = Path(target,"phase.json").read_text()
        self.assertNotIn("refresh",text)
        self.assertNotIn("token",text.lower())
        self.assertNotIn("crypt",text.lower())

    def test_invalid_bool_schema_blocks(self):
        target = self.prepared()
        data = json.loads(Path(target,"phase.json").read_text())
        data["schema"] = True
        Path(target,"phase.json").write_text(json.dumps(data))
        self.assertTrue(journal.needs_manual_recovery(self.parent))

    def test_missing_phase_file_blocks(self):
        target = self.prepared()
        Path(target,"phase.json").unlink()
        self.assertTrue(journal.needs_manual_recovery(self.parent))

    def test_no_systemctl_or_mount_invoked(self):
        text = (Path(__file__).resolve().parents[1] /
                "lib/rclone_two_mount_journal.py").read_text()
        self.assertNotIn("import subprocess",text)
        self.assertNotIn("systemctl ",text)
        self.assertNotIn("mount --bind",text)


if __name__=="__main__":
    unittest.main()
