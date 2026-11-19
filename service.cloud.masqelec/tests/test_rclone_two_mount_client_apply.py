# -*- coding: utf-8 -*-
"""End-to-end CLIENT recovery composition with mock services and real files."""
from pathlib import Path
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

from lib import rclone_two_mount_client_apply as apply


class ClientApplyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.conf = root / "config"
        self.conf.mkdir(mode=0o700)
        self.conf.chmod(0o700)
        self.journal = root / "journal"
        self.journal.mkdir(mode=0o700)
        self.journal.chmod(0o700)
        self.account = self.conf / "account1.conf"
        self.account.write_bytes(b"old")
        self.account.chmod(0o600)
        self.other = self.conf / "account2.conf"
        self.other.write_bytes(b"second-unchanged")
        self.other.chmod(0o600)
        self.events = []
        self.prepared = {
            "status": "candidate_requires_probe",
            "account_index": 0, "baseline_account": b"old",
            "candidate_account": b"new",
        }
        self.rpc = lambda request: '{"jsonrpc":"2.0","id":1,"result":[]}'

    def factory(self, index, *, enabled, media_check):
        self.events.append(("factory", index))
        def op(name):
            def invoke(i):
                self.events.append((name, i))
                return True
            return invoke
        return SimpleNamespace(
            stop=op("stop"), quiescent=op("quiescent"),
            start=op("start"), healthy=op("healthy"))

    def invoke(self, **overrides):
        params = dict(
            authorized=True, verified_probe=True, rpc_call=self.rpc,
            media_check=lambda _: True, adapter_factory=self.factory,
            account_path=str(self.account), journal_dir=str(self.journal))
        params.update(overrides)
        with mock.patch.object(
                apply.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                apply.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                apply.rollout, "mode", return_value="active"), mock.patch.object(
                apply.os, "geteuid", return_value=0), mock.patch.object(
                apply.guard, "client_recovery_pending", return_value=False):
            return apply.apply_verified(self.prepared, **params)

    def test_default_flags_block_without_side_effects(self):
        result = apply.apply_verified(self.prepared)
        self.assertEqual(result, "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.events, [])

    def test_disabled_flag_still_blocks(self):
        with mock.patch.object(
                apply.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                False):
            self.assertEqual(
                apply.apply_verified(self.prepared, authorized=True,
                                     verified_probe=True),
                "BLOCKED_RELEASE_GATES")

    def test_mock_service_transaction_with_real_disk(self):
        self.assertEqual(self.invoke(), "RECOVERED_VERIFIED")
        self.assertEqual(self.account.read_bytes(), b"new")
        self.assertEqual(self.other.read_bytes(), b"second-unchanged")
        self.assertEqual((self.journal / "account1.bak").read_bytes(), b"old")
        self.assertEqual(self.events[0], ("factory", 0))
        self.assertEqual(set(i for name, i in self.events), {0})

    def test_busy_playback_blocks_before_disk(self):
        busy = lambda request: (
            '{"jsonrpc":"2.0","id":1,"result":[{"playerid":1,"type":"video"}]}')
        self.assertEqual(self.invoke(rpc_call=busy),
                         "BLOCKED_PLAYBACK_OR_MEDIA")
        self.assertEqual(self.account.read_bytes(), b"old")

    def test_pending_recovery_blocks(self):
        with mock.patch.object(
                apply.guard, "client_recovery_pending", return_value=True):
            # Patch in invoke overrides inner patch? This test uses separate
            # targeted external guard through the real pending file instead.
            pass
        (self.journal / "state.json").write_text(
            '{"version":1,"account":0,"phase":"stop_requested"}')
        (self.journal / "state.json").chmod(0o600)
        self.assertEqual(self.invoke(), "BLOCKED_SNAPSHOT")
        self.assertEqual(self.account.read_bytes(), b"old")

    def test_bad_index_no_write(self):
        bad = dict(self.prepared, account_index=True)
        with mock.patch.object(
                apply.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                apply.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                apply.rollout, "mode", return_value="active"), mock.patch.object(
                apply.os, "geteuid", return_value=0):
            self.assertEqual(apply.apply_verified(
                bad, authorized=True, verified_probe=True,
                rpc_call=self.rpc, media_check=lambda _: True),
                "BLOCKED_CANDIDATE")


if __name__ == "__main__":
    unittest.main()
