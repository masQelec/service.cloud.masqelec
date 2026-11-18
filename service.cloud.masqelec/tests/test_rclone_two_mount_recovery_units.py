# -*- coding: utf-8 -*-
"""Overrides de rollback: config aislado; sin cambio de unidades originales."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_mount_isolation as isolation
from lib import rclone_two_mount_recovery_units as recovery
from lib import rclone_two_mount_rollout as rollout
from test_rclone_mount_isolation import sample_units


RECOVERY = (
    "/storage/.config/masqelec/rclone-v2-transaction/"
    + rollout.CANDIDATE_ID + "/canonical-recovery-candidate.conf"
)


class RecoveryOverridesTests(unittest.TestCase):
    def test_four_overrides_preserve_paths_and_flags(self):
        original = sample_units()
        results = recovery.overrides(original, RECOVERY)
        self.assertEqual(set(results), set(rollout.LEGACY_SERVICES))
        for unit in original:
            text = results[unit].decode()
            self.assertTrue(text.startswith(
                "[Service]\nExecStart=\nExecStart="))
            old_args = isolation._start_args(original[unit])
            new_args = isolation._start_args(results[unit])
            self.assertEqual(old_args[:4], new_args[:4])
            self.assertEqual(
                isolation._config_arg(new_args), RECOVERY)
            self.assertEqual(
                isolation._config_arg(old_args), isolation.LIVE_CONFIG)
            self.assertEqual(new_args[:4], old_args[:4])
            self.assertIn("--read-only", new_args)
            self.assertNotIn("refresh_token", text)
            self.assertNotIn("access_token", text)
            self.assertNotIn("https://", text)

    def test_original_units_are_never_mutated(self):
        original = sample_units()
        before = dict(original)
        recovery.overrides(original, RECOVERY)
        self.assertEqual(original, before)

    def test_relative_config_path_denied(self):
        for bad in ("recovery.conf", "/tmp/file", "/tmp/../else/"
                    "canonical-recovery-candidate.conf",
                    "/tmp/a\nExecStart=evil/"
                    "canonical-recovery-candidate.conf", "",
                    None):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                recovery.overrides(sample_units(), bad)

    def test_missing_legacy_unit_denied(self):
        units = sample_units()
        units.pop(next(iter(units)))
        with self.assertRaises(ValueError):
            recovery.overrides(units, RECOVERY)

    def test_tampered_command_denied(self):
        units = sample_units()
        target = rollout.LEGACY_SERVICES[0]
        units[target] = units[target].replace(
            b"--read-only", b"--allow-other")
        with self.assertRaises(ValueError):
            recovery.overrides(units, RECOVERY)

    def test_no_systemd_calls_or_filesystem_mutation(self):
        source = (Path(__file__).resolve().parents[1] /
                  "lib/rclone_two_mount_recovery_units.py").read_text()
        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.replace", source)
        self.assertNotIn("os.mkdir", source)


if __name__ == "__main__":
    unittest.main()
