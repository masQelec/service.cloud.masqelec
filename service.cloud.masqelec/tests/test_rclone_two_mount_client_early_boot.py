# -*- coding: utf-8 -*-
"""CLIENT early-boot coordinator; all systemd and Kodi calls simulated."""
import unittest
from unittest import mock
from lib import rclone_two_mount_client_early_boot as boot


class BootClientTests(unittest.TestCase):
    def test_default_disabled_does_no_io(self):
        with mock.patch.object(boot, "_get_role",
                               side_effect=AssertionError("no role lookup")):
            self.assertEqual(boot.execute(), "BLOCKED_NOT_AUTHORIZED")

    def test_root_and_role_gate(self):
        with mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                boot, "_is_root", return_value=False):
            self.assertEqual(boot.execute(authorized=True), "BLOCKED_NOT_ROOT")
        with mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                boot, "_is_root", return_value=True), mock.patch.object(
                boot, "_get_role", return_value="MASTER"):
            self.assertEqual(boot.execute(authorized=True), "BLOCKED_NOT_CLIENT")

    def test_only_pending_account_is_recovered(self):
        called = []
        class Machine:
            def __init__(self, i, **kwargs):
                called.append(("machine", i))
        def restore(i, **kwargs):
            called.append(("recover", i))
            return "ROLLED_BACK_VERIFIED"
        with mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                boot, "_is_root", return_value=True), mock.patch.object(
                boot, "_get_role", return_value="CLIENT"), mock.patch.object(
                boot.rollout, "mode", return_value="active"), mock.patch.object(
                boot.early, "kodi_process_absent", return_value=True), mock.patch.object(
                boot.guard, "client_recovery_pending",
                side_effect=[True, False]), mock.patch.object(
                boot.files, "recovery_pending", side_effect=[True, False]), mock.patch.object(
                boot.crash, "restore_interrupted", side_effect=restore):
            result = boot.execute(
                authorized=True, parent="/tmp/fake-private-recovery",
                media_paths=("a", "b"), adapter_factory=Machine)
        self.assertEqual(result, "ROLLED_BACK_VERIFIED")
        self.assertEqual(called, [("machine", 0), ("recover", 0)])

    def test_unsafe_kodi_blocks_before_any_service(self):
        with mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                boot, "_is_root", return_value=True), mock.patch.object(
                boot, "_get_role", return_value="CLIENT"), mock.patch.object(
                boot.rollout, "mode", return_value="active"), mock.patch.object(
                boot.early, "kodi_process_absent", return_value=False), mock.patch.object(
                boot.crash, "restore_interrupted") as restore:
            self.assertEqual(boot.execute(authorized=True),
                             "BLOCKED_KODI_RUNNING_OR_UNKNOWN")
            restore.assert_not_called()

    def test_failed_restore_keeps_manual_block(self):
        with mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                boot.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                True), mock.patch.object(
                boot, "_is_root", return_value=True), mock.patch.object(
                boot, "_get_role", return_value="CLIENT"), mock.patch.object(
                boot.rollout, "mode", return_value="active"), mock.patch.object(
                boot.early, "kodi_process_absent", return_value=True), mock.patch.object(
                boot.guard, "client_recovery_pending", return_value=True), mock.patch.object(
                boot.files, "recovery_pending", return_value=True), mock.patch.object(
                boot.crash, "restore_interrupted",
                return_value="MANUAL_RECOVERY_REQUIRED"):
            self.assertEqual(boot.execute(
                authorized=True, parent="/tmp/test",
                media_paths=("a", "b"), adapter_factory=lambda i, **kw: object()),
                "MANUAL_RECOVERY_REQUIRED")


if __name__ == "__main__":
    unittest.main()
