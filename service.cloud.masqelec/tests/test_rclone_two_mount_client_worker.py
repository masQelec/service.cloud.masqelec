# -*- coding: utf-8 -*-
"""CLIENT periodic worker: no IO when gated, one-account AUTH only."""
import unittest
from unittest import mock

from lib import rclone_two_mount_client_worker as worker


class WorkerTests(unittest.TestCase):
    def setUp(self):
        worker._last_attempt = None
        self.addCleanup(setattr, worker, "_last_attempt", None)
        self.calls = []
        self.rpc = lambda _: '{"jsonrpc":"2.0","id":1,"result":[]}'

    def test_default_disabled_does_not_read_sources(self):
        source = mock.Mock(side_effect=AssertionError("must not access secrets"))
        self.assertEqual(worker.tick(self.rpc, read_sources=source),
                         "BLOCKED_NOT_AUTHORIZED")
        source.assert_not_called()

    def test_released_flag_still_denied_when_role_not_client(self):
        with mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                worker, "rollout") as rollout:
            self.assertEqual(worker.tick(
                self.rpc, authorized=True, role="MASTER"),
                "BLOCKED_NOT_CLIENT")
            rollout.mode.assert_not_called()

    def test_only_auth_for_second_account_invokes_recovery(self):
        with mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                worker, "rollout") as rollout, mock.patch.object(
                worker.guard, "client_recovery_pending",
                return_value=False), mock.patch.object(
                worker, "_auth_state",
                side_effect=["unavailable", "auth"]), mock.patch.object(
                worker.apply, "recover_one", return_value="RECOVERED_VERIFIED") as recover:
            rollout.mode.return_value = "active"
            result = worker.tick(
                self.rpc, authorized=True, role="CLIENT", now=1000,
                read_sources=lambda: (b"canonical", (b"one", b"two")),
                key=b"key", transport=mock.Mock(),
                known=("media1", "media2"), probe=lambda i, b: "ok")
        self.assertEqual(result, "RECOVERED_VERIFIED")
        self.assertEqual(recover.call_count, 1)
        self.assertEqual(recover.call_args.kwargs["account_index"], 1)
        self.assertEqual(recover.call_args.kwargs["auth_status"], "auth")

    def test_busy_playback_blocks_network_probes(self):
        with mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                worker.rollout, "mode", return_value="active"), mock.patch.object(
                worker.guard, "client_recovery_pending",
                return_value=False), mock.patch.object(
                worker, "_auth_state", side_effect=AssertionError("no probe")):
            self.assertEqual(worker.tick(
                lambda _: '{"jsonrpc":"2.0","id":1,"result":[{"playerid":1}]}',
                authorized=True, role="CLIENT", now=100),
                "DEFERRED_PLAYBACK")

    def test_probe_interval(self):
        worker._last_attempt = 100
        with mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                worker.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                worker.rollout, "mode", return_value="active"), mock.patch.object(
                worker.guard, "client_recovery_pending",
                return_value=False):
            self.assertEqual(worker.tick(
                self.rpc, authorized=True, role="CLIENT", now=101),
                "DEFERRED_INTERVAL")


if __name__ == "__main__":
    unittest.main()
