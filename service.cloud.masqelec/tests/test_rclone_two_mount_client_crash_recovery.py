# -*- coding: utf-8 -*-
"""Reboot recovery with real private files, fake per-account services."""
import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace

from lib import rclone_two_mount_client_crash_recovery as crash
from lib import rclone_two_mount_client_file_ops as files


class CrashRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.conf = root / "private"
        self.conf.mkdir(mode=0o700)
        self.conf.chmod(0o700)
        self.journal = root / "txn"
        self.journal.mkdir(mode=0o700)
        self.journal.chmod(0o700)
        self.account = self.conf / "account1.conf"
        self.account.write_bytes(b"candidate")
        self.account.chmod(0o600)
        self.other = self.conf / "account2.conf"
        self.other.write_bytes(b"other untouched")
        self.other.chmod(0o600)
        backup = self.journal / "account1.bak"
        backup.write_bytes(b"original")
        backup.chmod(0o600)
        self.phase("install_requested")
        self.events = []
        self.fail = None

    def phase(self, name, account=0):
        path = self.journal / "state.json"
        path.write_text(json.dumps({
            "version": 1, "account": account, "phase": name
        }))
        path.chmod(0o600)

    def services(self):
        def cb(name):
            def run(index):
                self.events.append((name, index))
                return name != self.fail
            return run
        return SimpleNamespace(stop=cb("stop"),
                               quiescent=cb("quiescent"),
                               start=cb("start"),
                               healthy=cb("healthy"))

    def recover(self, **kwargs):
        params = dict(index=0, account_path=str(self.account),
                      journal_dir=str(self.journal),
                      services=self.services(), authorized=True)
        params.update(kwargs)
        return crash.restore_interrupted(**params)

    def test_interrupted_install_restore_and_verify(self):
        self.assertEqual(self.recover(), "ROLLED_BACK_VERIFIED")
        self.assertEqual(self.account.read_bytes(), b"original")
        self.assertEqual(self.other.read_bytes(), b"other untouched")
        self.assertFalse(files.recovery_pending(str(self.journal), 0))
        self.assertEqual(self.recover(), "ALREADY_FINALIZED")
        self.assertEqual([n for n, _ in self.events],
                         ["stop", "quiescent", "start", "healthy"])

    def test_stop_failure_preserves_unfinished_journal(self):
        self.fail = "stop"
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"candidate")
        self.assertTrue(files.recovery_pending(str(self.journal), 0))

    def test_quiescence_failure_cannot_change_bytes(self):
        self.fail = "quiescent"
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"candidate")

    def test_health_failure_keeps_guard_after_restoring_bytes(self):
        self.fail = "healthy"
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"original")
        self.assertTrue(files.recovery_pending(str(self.journal), 0))

    def test_retry_after_failed_health_is_idempotent(self):
        self.fail = "healthy"
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.fail = None
        self.assertEqual(self.recover(), "ROLLED_BACK_VERIFIED")
        self.assertEqual(self.account.read_bytes(), b"original")

    def test_mismatched_account_state_blocks_before_services(self):
        self.phase("install_requested", account=1)
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.events, [])

    def test_corrupt_state_cannot_modify(self):
        (self.journal / "state.json").write_text("not json")
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"candidate")

    def test_missing_backup_cannot_modify(self):
        (self.journal / "account1.bak").unlink()
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.events, [])

    def test_completed_transaction_does_not_restore_stale_backup(self):
        self.phase("committed")
        self.assertEqual(self.recover(), "ALREADY_FINALIZED")
        self.assertEqual(self.account.read_bytes(), b"candidate")
        self.assertEqual(self.events, [])

    def test_disallowed_by_default(self):
        self.assertEqual(self.recover(authorized=False), "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.events, [])

    def test_no_foreign_account_or_symlink(self):
        self.assertEqual(self.recover(index=1), "BLOCKED_ACCOUNT")
        self.assertEqual(self.events, [])
        (self.journal / "account1.bak").unlink()
        (self.journal / "account1.bak").symlink_to(self.other)
        self.assertEqual(self.recover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.other.read_bytes(), b"other untouched")


if __name__ == "__main__":
    unittest.main()
