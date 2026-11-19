# -*- coding: utf-8 -*-
"""A media recovery fault must not cause Kodi boot dependency failure."""
import contextlib
import importlib.util
import io
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

    def test_invalid_mode_never_attempts_recovery(self):
        with mock.patch.object(runner.early, "execute",
                               side_effect=AssertionError("no call")):
            self.assertEqual(runner.main(["--apply"]), 0)


if __name__ == "__main__":
    unittest.main()
