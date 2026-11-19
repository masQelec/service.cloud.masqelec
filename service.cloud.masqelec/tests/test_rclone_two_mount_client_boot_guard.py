# -*- coding: utf-8 -*-
"""Crash guard for a CLIENT recovery, local fixtures only."""
import os
from pathlib import Path
import tempfile
import unittest
from lib import rclone_two_mount_boot_guard as guard


class ClientBootGuardTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.parent = Path(self.t.name) / "recovery"
        self.parent.mkdir(mode=0o700)
        self.parent.chmod(0o700)

    def test_absent_journals_safe(self):
        self.assertFalse(guard.client_recovery_pending(str(self.parent)))

    def test_partial_journal_blocks(self):
        a = self.parent / "account1"
        a.mkdir(mode=0o700)
        a.chmod(0o700)
        f = a / "state.json"
        f.write_text('{"version":1,"account":0,"phase":"install_requested"}')
        f.chmod(0o600)
        self.assertTrue(guard.client_recovery_pending(str(self.parent)))

    def test_corrupt_journal_blocks(self):
        a = self.parent / "account2"
        a.mkdir(mode=0o700)
        a.chmod(0o700)
        f = a / "state.json"
        f.write_bytes(b"{")
        f.chmod(0o600)
        self.assertTrue(guard.client_recovery_pending(str(self.parent)))

    def test_committed_journal_no_block(self):
        a = self.parent / "account1"
        a.mkdir(mode=0o700)
        a.chmod(0o700)
        f = a / "state.json"
        f.write_text('{"version":1,"account":0,"phase":"committed"}')
        f.chmod(0o600)
        self.assertFalse(guard.client_recovery_pending(str(self.parent)))

    def test_symlink_journal_blocks(self):
        (self.parent / "account1").symlink_to(self.parent)
        self.assertTrue(guard.client_recovery_pending(str(self.parent)))

    def test_client_guard_can_block_global_guard(self):
        with tempfile.TemporaryDirectory() as base:
            partial = self.parent / "account2"
            partial.mkdir(mode=0o700)
            partial.chmod(0o700)
            f = partial / "account2.bak"
            f.write_bytes(b"backup")
            f.chmod(0o600)
            with unittest.mock.patch.object(
                    guard, "CLIENT_TXN_PARENT", str(self.parent)):
                self.assertTrue(guard.recovery_required(
                    parent=base, state_path=os.path.join(base, "missing")))


if __name__ == "__main__":
    unittest.main()
