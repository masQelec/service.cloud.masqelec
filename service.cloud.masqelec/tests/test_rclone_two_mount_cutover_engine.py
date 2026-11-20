# -*- coding: utf-8 -*-
"""Inyección de fallos en la secuencia cutover/rollback, sin montajes."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_cutover_engine as engine


class FakeAdapter:
    def __init__(self, fails=(), unhealthy=()):
        self.log = []
        self.fails = set(fails)
        self.unhealthy = set(unhealthy)

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def call():
            self.log.append(name)
            if name in self.fails:
                raise RuntimeError("private-synthetic-fault")
            return name not in self.unhealthy
        return call


class CutoverEngineTests(unittest.TestCase):
    def run_enabled(self, fake):
        return engine.run(fake, release_authorized=True,
                          playback_idle=True, rollback_ready=True)

    def test_default_fences_without_adapter_io(self):
        fake = FakeAdapter()
        self.assertEqual(engine.run(fake), "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(fake.log, [])

    def test_playback_approval_required(self):
        fake = FakeAdapter()
        self.assertEqual(engine.run(fake, release_authorized=True),
                         "BLOCKED_PLAYBACK_NOT_VERIFIED")
        self.assertEqual(fake.log, [])

    def test_rollback_approval_required(self):
        fake = FakeAdapter()
        self.assertEqual(engine.run(fake, release_authorized=True,
                                    playback_idle=True),
                         "BLOCKED_ROLLBACK_NOT_READY")
        self.assertEqual(fake.log, [])

    def test_nonboolean_fences_fail_closed(self):
        for values in (
                dict(release_authorized=1),
                dict(release_authorized=True, playback_idle="yes"),
                dict(release_authorized=True, playback_idle=True,
                     rollback_ready=1)):
            fake = FakeAdapter()
            self.assertEqual(engine.run(fake, **values),
                             "BLOCKED_INVALID_GATES")
            self.assertEqual(fake.log, [])

    def test_preflight_failure_prevents_mutation(self):
        fake = FakeAdapter(unhealthy={"legacy_preflight"})
        self.assertEqual(self.run_enabled(fake), "BLOCKED_LEGACY_PREFLIGHT")
        self.assertEqual(fake.log, ["legacy_preflight"])

    def test_prepare_failure_prevents_mutation(self):
        fake = FakeAdapter(unhealthy={"prepare_durable_rollback"})
        self.assertEqual(self.run_enabled(fake),
                         "BLOCKED_ROLLBACK_PREPARATION")
        self.assertNotIn("stop_legacy", fake.log)

    def test_playback_changed_prevents_mutation(self):
        fake = FakeAdapter(unhealthy={"playback_still_idle"})
        self.assertEqual(self.run_enabled(fake), "BLOCKED_PLAYBACK_CHANGED")
        self.assertNotIn("prepare_durable_rollback", fake.log)

    def test_success_order_and_final_marker(self):
        fake = FakeAdapter()
        self.assertEqual(self.run_enabled(fake), "ACTIVE")
        self.assertEqual(fake.log, [
            "legacy_preflight", "playback_still_idle",
            "prepare_durable_rollback", "mark_cutover_started",
            "stop_legacy", "legacy_fully_unmounted", "install_current_v2",
            "start_fuse", "fuse_ready", "start_binds",
            "complete_health", "playback_still_idle", "mark_active"])

    def test_all_failures_enter_rollback(self):
        for phase in ("mark_cutover_started", "stop_legacy",
                      "install_current_v2", "start_fuse",
                      "start_binds", "mark_active"):
            with self.subTest(phase=phase):
                fake = FakeAdapter(fails={phase})
                self.assertEqual(self.run_enabled(fake), "ROLLED_BACK")
                self.assertIn("stop_binds", fake.log)
                self.assertIn("stop_fuse", fake.log)
                self.assertIn("reconcile_and_restore_legacy", fake.log)
                self.assertEqual(fake.log[-1], "mark_legacy_restored")

    def test_legacy_mount_still_present_rolls_back(self):
        fake = FakeAdapter(unhealthy={"legacy_fully_unmounted"})
        self.assertEqual(self.run_enabled(fake), "ROLLED_BACK")
        self.assertNotIn("install_current_v2", fake.log)

    def test_missing_fuse_rolls_back(self):
        fake = FakeAdapter(unhealthy={"fuse_ready"})
        self.assertEqual(self.run_enabled(fake), "ROLLED_BACK")
        self.assertNotIn("start_binds", fake.log)

    def test_bad_mount_layout_rolls_back(self):
        fake = FakeAdapter(unhealthy={"complete_health"})
        self.assertEqual(self.run_enabled(fake), "ROLLED_BACK")

    def test_playback_race_after_start_rolls_back(self):
        class ChangesAfterStart(FakeAdapter):
            def playback_still_idle(self):
                self.log.append("playback_still_idle")
                return self.log.count("playback_still_idle") == 1
        fake = ChangesAfterStart()
        self.assertEqual(self.run_enabled(fake), "ROLLED_BACK")
        self.assertNotIn("mark_active", fake.log)

    def test_failure_to_stop_binds_blocks_rollback(self):
        fake = FakeAdapter(fails={"start_binds", "stop_binds"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertNotIn("reconcile_and_restore_legacy", fake.log)

    def test_failure_to_stop_fuse_blocks_rollback(self):
        fake = FakeAdapter(fails={"start_fuse", "stop_fuse"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertNotIn("reconcile_and_restore_legacy", fake.log)

    def test_new_mounts_still_present_blocks_rollback(self):
        fake = FakeAdapter(unhealthy={"complete_health",
                                      "new_fully_unmounted"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertNotIn("reconcile_and_restore_legacy", fake.log)

    def test_failed_token_reconciliation_blocks_legacy_start(self):
        fake = FakeAdapter(fails={"complete_health",
                                  "reconcile_and_restore_legacy"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertNotIn("start_legacy", fake.log)

    def test_failed_legacy_start_never_marks_legacy(self):
        fake = FakeAdapter(fails={"start_binds", "start_legacy"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertNotIn("mark_legacy_restored", fake.log)

    def test_failed_legacy_health_blocks_marker(self):
        fake = FakeAdapter(unhealthy={"complete_health",
                                      "legacy_healthy"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")
        self.assertNotIn("mark_legacy_restored", fake.log)

    def test_failed_legacy_marker_blocks_success(self):
        fake = FakeAdapter(fails={"complete_health",
                                  "mark_legacy_restored"})
        self.assertEqual(self.run_enabled(fake),
                         "MANUAL_RECOVERY_REQUIRED")

    def test_no_real_mount_or_network_functions_in_engine(self):
        text = (Path(__file__).resolve().parents[1] /
                "lib/rclone_two_mount_cutover_engine.py").read_text()
        for forbidden in ("import subprocess", "import urllib",
                          "os.system(", "systemctl start", "rclone lsf"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
