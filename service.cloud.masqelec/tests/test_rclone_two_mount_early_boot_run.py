# -*- coding: utf-8 -*-
"""A media recovery fault must not cause Kodi boot dependency failure."""
import contextlib
import importlib.util
import io
import tempfile
from pathlib import Path
import unittest
from unittest import mock

script = (Path(__file__).resolve().parents[1] /
          "tools/rclone_two_mount_early_boot_run.py")
spec = importlib.util.spec_from_file_location("early_boot_run", script)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def test_failure_does_not_fail_kodi_boot(self):
        with mock.patch.object(runner.early, "execute",
                               return_value="MANUAL_RECOVERY_REQUIRED"):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--recover"]), 0)
        self.assertIn("MANUAL_RECOVERY_REQUIRED", output.getvalue())

    def test_unexpected_failure_does_not_print_secret_or_stop_kodi(self):
        with mock.patch.object(runner.early, "execute",
                               side_effect=RuntimeError("secret-token")):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--recover"]), 0)
        self.assertIn("MANUAL_RECOVERY_REQUIRED", output.getvalue())
        self.assertNotIn("secret-token", output.getvalue())

    def test_success_does_not_fail_kodi_boot(self):
        with mock.patch.object(runner.early, "execute",
                               return_value="ROLLED_BACK"):
            self.assertEqual(runner.main(["--recover"]), 0)

    def test_unknown_result_never_prints_untrusted_content(self):
        with mock.patch.object(runner.early, "execute",
                               return_value="refresh_token=SECRET"):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(runner.main(["--recover"]), 0)
        self.assertNotIn("SECRET", output.getvalue())
        self.assertIn("MANUAL_RECOVERY_REQUIRED", output.getvalue())

    def test_dev_fake_recovery_opt_in_disabled_by_default(self):
        with mock.patch.object(
                runner.constants,
                "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED", False):
            self.assertEqual(runner._dev_fake_boot_lab(), "DISABLED")

    def test_dev_fake_recovery_refuses_real_recovery_flags(self):
        with mock.patch.object(
                runner.constants,
                "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED", True), \
             mock.patch.object(
                runner.constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", True):
            self.assertEqual(runner._dev_fake_boot_lab(),
                             "BLOCKED_REAL_RECOVERY_ENABLED")

    def test_dev_fake_recovery_invoked_only_in_real_recover_mode(self):
        with mock.patch.object(runner, "_dev_fake_boot_lab",
                               return_value="PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK") as lab, \
             mock.patch.object(runner.early, "execute",
                               return_value="BLOCKED_NOT_AUTHORIZED"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["--recover"]), 0)
        lab.assert_called_once_with()
        self.assertIn("MASQELEC_DEV_FAKE_BOOT_LAB=PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK",
                      output.getvalue())
        self.assertIn("MASQELEC_EARLY_BOOT=BLOCKED_NOT_AUTHORIZED",
                      output.getvalue())

    def test_pending_fake_lab_requires_kodi_absent(self):
        with mock.patch.object(
                runner.constants, "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
                True), \
             mock.patch.object(runner.early, "kodi_process_absent",
                               return_value=False), \
             mock.patch("tools.rclone_two_mount_reboot_journal_lab.verify",
                        side_effect=AssertionError("must not write")) as verify, \
             mock.patch("tools.rclone_two_mount_reboot_journal_lab.os.path.lexists",
                        return_value=True):
            self.assertEqual(runner._dev_fake_boot_lab(),
                             "BLOCKED_KODI_RUNNING_OR_UNKNOWN")
            verify.assert_not_called()

    def test_real_runner_uses_fake_journal_verify_api(self):
        from tools import rclone_two_mount_reboot_journal_lab as lab
        boot_a = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        boot_b = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "journal"
            with mock.patch.object(lab, "ROOT", root), \
                 mock.patch.object(lab, "_is_root", return_value=True), \
                 mock.patch.object(lab, "_mounts_clear", return_value=True), \
                 mock.patch.object(lab, "_boot_id", return_value=boot_a):
                self.assertEqual(lab.prepare(), "PREPARED_REBOOT_REQUIRED")
                with mock.patch.object(
                        runner.constants,
                        "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED", True), \
                     mock.patch.object(runner.early, "kodi_process_absent",
                                       return_value=True), \
                     mock.patch.object(lab, "_boot_id", return_value=boot_b):
                    self.assertEqual(
                        runner._dev_fake_boot_lab(),
                        "PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK")
                self.assertFalse(root.exists())

    def test_invalid_mode_never_runs_dev_fake_recovery(self):
        with mock.patch.object(runner, "_dev_fake_boot_lab",
                               side_effect=AssertionError("must not run")):
            self.assertEqual(runner.main(["--apply"]), 0)

    def test_dev_fake_recovery_failure_cannot_leak_exception_text(self):
        with mock.patch.object(runner, "_dev_fake_boot_lab",
                               return_value="MANUAL_RECOVERY_REQUIRED"), \
             mock.patch.object(runner.early, "execute",
                               return_value="BLOCKED_NOT_AUTHORIZED"), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(runner.main(["--recover"]), 0)
        self.assertIn("MASQELEC_DEV_FAKE_BOOT_LAB=MANUAL_RECOVERY_REQUIRED",
                      output.getvalue())

    def test_enabled_client_recovery_uses_headless_role_and_client_path(self):
        from lib import rclone_two_mount_client_early_boot as client
        with mock.patch.object(
                runner.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                client, "_get_role", return_value="CLIENT") as identity, mock.patch.object(
                client, "execute", return_value="NO_PENDING") as recover, mock.patch.object(
                runner.early, "execute", side_effect=AssertionError(
                    "Must not use MASTER cutover recovery")), mock.patch.object(
                runner, "_dev_fake_boot_lab", return_value="DISABLED"), contextlib.redirect_stdout(
                io.StringIO()) as output:
            self.assertEqual(runner.main(["--recover"]), 0)
        identity.assert_called()
        recover.assert_called_once_with(authorized=True)
        self.assertIn("MASQELEC_EARLY_BOOT=NO_PENDING", output.getvalue())

    def test_unknown_role_never_invokes_any_real_recovery(self):
        from lib import rclone_two_mount_client_early_boot as client
        with mock.patch.object(
                runner.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                client, "_get_role", return_value="UNKNOWN"), mock.patch.object(
                client, "execute", side_effect=AssertionError(
                    "No CLIENT recovery")) as recovery, mock.patch.object(
                runner.early, "execute", side_effect=AssertionError(
                    "No MASTER recovery")) as legacy, mock.patch.object(
                runner, "_dev_fake_boot_lab", return_value="DISABLED"), contextlib.redirect_stdout(
                io.StringIO()) as output:
            self.assertEqual(runner.main(["--recover"]), 0)
        recovery.assert_not_called()
        legacy.assert_not_called()
        self.assertIn("MASQELEC_EARLY_BOOT=BLOCKED_ROLE_UNAVAILABLE", output.getvalue())

    def test_real_master_without_override_retains_master_rollback(self):
        from lib import rclone_two_mount_client_early_boot as client
        with mock.patch.object(
                runner.constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                True), mock.patch.object(
                runner.constants, "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
                False), mock.patch.object(
                client, "_get_role", return_value="MASTER"), mock.patch.object(
                client, "execute", side_effect=AssertionError(
                    "No CLIENT override")), mock.patch.object(
                runner.early, "execute", return_value="NO_PENDING") as legacy, mock.patch.object(
                runner, "_dev_fake_boot_lab", return_value="DISABLED"):
            self.assertEqual(runner.main(["--recover"]), 0)
        legacy.assert_called_once()

    def test_invalid_mode_never_attempts_recovery(self):
        with mock.patch.object(runner.early, "execute",
                               side_effect=AssertionError("no call")):
            self.assertEqual(runner.main(["--apply"]), 0)


if __name__ == "__main__":
    unittest.main()
