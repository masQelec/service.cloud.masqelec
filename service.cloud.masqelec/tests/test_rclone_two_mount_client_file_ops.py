# -*- coding: utf-8 -*-
"""Real file/fsync test in disposable /tmp, no OAuth or systemd."""
import os
from pathlib import Path
import stat
import tempfile
import unittest

from lib import rclone_two_mount_client_file_ops as files
from lib import rclone_two_mount_client_transaction as tx


class AccountFileOpsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.root = root
        self.conf = root / "configs"
        self.conf.mkdir(mode=0o700)
        self.conf.chmod(0o700)
        self.journal = root / "txn"
        self.journal.mkdir(mode=0o700)
        self.journal.chmod(0o700)
        self.account = self.conf / "account1.conf"
        self.account.write_bytes(b"old-oauth")
        self.account.chmod(0o600)
        self.other = self.conf / "account2.conf"
        self.other.write_bytes(b"unrelated-account")
        self.other.chmod(0o600)
        self.calls = []
        self.fail = None

    def callback(self, label):
        def run(index):
            self.calls.append((label, index))
            return label != self.fail
        return run

    def ops(self, enabled=True):
        return files.AccountFileOps(
            0, account_path=str(self.account),
            journal_dir=str(self.journal),
            stop=self.callback("stop"),
            quiescent=self.callback("quiescent"),
            start=self.callback("start"),
            healthy=self.callback("healthy"),
            enabled=enabled)

    def candidate(self):
        return {"status": "candidate_requires_probe",
                "account_index": 0,
                "baseline_account": b"old-oauth",
                "candidate_account": b"new-oauth"}

    def execute(self, operations):
        with files.locked(str(self.journal)):
            return tx.execute(self.candidate(), authorized=True,
                              verified_probe=True, playback_idle=True,
                              operations=operations)

    def test_disabled_cannot_write(self):
        self.assertEqual(self.execute(self.ops(enabled=False)),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"old-oauth")
        self.assertEqual(self.other.read_bytes(), b"unrelated-account")

    def test_success_changes_only_target_and_retains_backup(self):
        self.assertEqual(self.execute(self.ops()), "RECOVERED_VERIFIED")
        self.assertEqual(self.account.read_bytes(), b"new-oauth")
        self.assertEqual(self.other.read_bytes(), b"unrelated-account")
        self.assertEqual((self.journal / "account1.bak").read_bytes(),
                         b"old-oauth")
        self.assertEqual(stat.S_IMODE(self.account.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(
            (self.journal / "account1.bak").stat().st_mode), 0o600)
        self.assertFalse(files.recovery_pending(str(self.journal)))
        # Idempotence must block, not overwrite backed-up credentials.
        self.assertEqual(self.execute(self.ops()), "BLOCKED_SNAPSHOT")

    def test_failure_after_install_rolls_back(self):
        self.fail = "healthy"
        self.assertEqual(self.execute(self.ops()), "MANUAL_RECOVERY_REQUIRED")
        # Failure of the health callback also means the rollback health
        # cannot be attested, even when old bytes were restored.
        self.assertEqual(self.account.read_bytes(), b"old-oauth")
        self.assertEqual(self.other.read_bytes(), b"unrelated-account")
        self.assertTrue(files.recovery_pending(str(self.journal)))

    def test_failure_before_install_rolls_back(self):
        self.fail = "quiescent"
        self.assertEqual(self.execute(self.ops()), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"old-oauth")

    def test_rollback_verified_after_install_failure(self):
        class FailOnce:
            pass
        adapter = self.ops()
        original = adapter.install
        adapter.install = lambda idx, content: False
        self.assertEqual(self.execute(adapter), "ROLLED_BACK_VERIFIED")
        self.assertEqual(self.account.read_bytes(), b"old-oauth")
        self.assertFalse(files.recovery_pending(str(self.journal)))
        self.assertEqual(self.other.read_bytes(), b"unrelated-account")

    def test_unfinished_state_blocks_new_attempt(self):
        (self.journal / "state.json").write_text(
            '{"version":1,"account":0,"phase":"stop_requested"}')
        (self.journal / "state.json").chmod(0o600)
        self.assertTrue(files.recovery_pending(str(self.journal)))
        self.assertEqual(self.execute(self.ops()), "BLOCKED_SNAPSHOT")
        self.assertEqual(self.account.read_bytes(), b"old-oauth")

    def test_backup_without_state_is_pending(self):
        (self.journal / "account1.bak").write_bytes(b"old-oauth")
        self.assertTrue(files.recovery_pending(str(self.journal)))

    def test_bad_permissions_block_before_mutation(self):
        self.conf.chmod(0o775)
        self.assertEqual(self.execute(self.ops()), "MANUAL_RECOVERY_REQUIRED")
        self.assertEqual(self.account.read_bytes(), b"old-oauth")

    def test_account_name_mismatch_rejected(self):
        with self.assertRaises(ValueError):
            files.AccountFileOps(
                1, account_path=str(self.account),
                journal_dir=str(self.journal),
                stop=self.callback("stop"), quiescent=self.callback("quiescent"),
                start=self.callback("start"), healthy=self.callback("healthy"),
                enabled=True)

    def test_provision_only_private_account_journal(self):
        root = self.root / "private-base"
        root.mkdir(mode=0o700)
        root.chmod(0o700)
        child = root / "client-recovery" / "account1"
        self.assertTrue(files.provision_private_journal(str(child)))
        self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE(child.parent.stat().st_mode), 0o700)
        self.assertTrue(files.provision_private_journal(str(child)))

    def test_provision_rejects_untrusted_ancestor_or_symlink(self):
        root = self.root / "untrusted-base"
        root.mkdir(mode=0o700)
        root.chmod(0o777)
        child = root / "client-recovery" / "account1"
        with self.assertRaises(ValueError):
            files.provision_private_journal(str(child))
        self.assertFalse(child.exists())
        root.chmod(0o700)
        (root / "client-recovery").symlink_to(self.journal)
        with self.assertRaises(ValueError):
            files.provision_private_journal(str(child))

    def test_lock_rejects_symlink(self):
        (self.journal / ".lock").symlink_to(self.account)
        with self.assertRaises(OSError):
            with files.locked(str(self.journal)):
                pass


if __name__ == "__main__":
    unittest.main()
