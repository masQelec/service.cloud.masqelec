# -*- coding: utf-8 -*-
"""Read-only readiness gate regression; no live mount/systemd mutations."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

P = Path(__file__).resolve().parents[1] / "tools/rclone_two_mount_cutover_readiness.py"
spec = importlib.util.spec_from_file_location("masqelec_cutover_readiness", P)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class ReadinessTests(unittest.TestCase):
    def _ready(self):
        stack = []
        def set_value(obj, key, value):
            patch = mock.patch.object(obj, key, value)
            patch.start()
            stack.append(patch)
        self.addCleanup(lambda: [p.stop() for p in reversed(stack)])
        set_value(gate.os, "geteuid", lambda: 0)
        set_value(gate, "ADDON", Path("/storage/.kodi/addons/service.cloud.masqelec"))
        for key in gate.REQUIRED_FLAGS_OFF:
            set_value(gate.constants, key, False)
        set_value(gate.preflight, "_read_role_standalone", lambda: "MASTER")
        set_value(gate.rollout, "mode", lambda allowed: "legacy")
        set_value(gate, "_staged_exact", lambda: True)
        set_value(gate, "_mounted_legacy_exact", lambda: True)
        set_value(gate.preflight, "_systemd_value", lambda u, prop: "active")
        set_value(gate, "_boot_order", lambda: True)
        set_value(gate.guard, "client_recovery_pending", lambda: False)
        set_value(gate.os.path, "lexists", lambda path: False)
        set_value(gate, "_media_samples_present", lambda: True)

    def test_invalid_mode_cannot_run_preflight(self):
        with mock.patch.object(gate, "inspect", side_effect=AssertionError):
            self.assertEqual(gate.main(["--execute"]), 2)

    def test_safe_readiness_does_not_authorize_cutover(self):
        self._ready()
        result = gate.inspect()
        self.assertEqual(result["CUTOVER_READINESS"], "PASS_PREPARED_NO_ACTIVATION")
        self.assertEqual(result["CUTOVER_EXECUTED"], "NO")
        self.assertEqual(result["RELEASE_AUTHORIZED"], "NO")
        self.assertEqual(result["KODI_IDLE_CONFIRMED"], "NO_EXECUTION_TIME_RPC")

    def test_stale_staging_fails_closed(self):
        self._ready()
        with mock.patch.object(gate, "_staged_exact", return_value=False):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_PHYSICAL_PRECONDITIONS")

    def test_missing_media_blocks(self):
        self._ready()
        with mock.patch.object(gate, "_media_samples_present", return_value=False):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_PHYSICAL_PRECONDITIONS")

    def test_mounted_legacy_missing_blocks(self):
        self._ready()
        with mock.patch.object(gate, "_mounted_legacy_exact", return_value=False):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_PHYSICAL_PRECONDITIONS")

    def test_boot_order_missing_blocks(self):
        self._ready()
        with mock.patch.object(gate, "_boot_order", return_value=False):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_PHYSICAL_PRECONDITIONS")

    def test_journal_pending_blocks(self):
        self._ready()
        with mock.patch.object(gate.guard, "client_recovery_pending", return_value=True):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_PHYSICAL_PRECONDITIONS")

    def test_real_release_flag_blocks(self):
        self._ready()
        with mock.patch.object(gate.constants,
                               "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", True):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_FEATURE_FLAGS")

    def test_wrong_role_blocks(self):
        self._ready()
        with mock.patch.object(gate.preflight, "_read_role_standalone",
                               return_value="CLIENT"):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_NOT_DEV_MASTER")

    def test_marker_exists_blocks(self):
        self._ready()
        with mock.patch.object(gate.os.path, "lexists", return_value=True):
            self.assertEqual(gate.inspect()["CUTOVER_READINESS"],
                             "BLOCKED_PHYSICAL_PRECONDITIONS")

    def test_unexpected_failure_only_prints_closed_status(self):
        with mock.patch.object(gate, "inspect",
                               side_effect=ValueError("private OAuth secret")):
            self.assertEqual(gate.main(["--read-only"]), 2)


if __name__ == "__main__":
    unittest.main()
