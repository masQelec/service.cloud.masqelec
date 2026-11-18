# -*- coding: utf-8 -*-
"""Pruebas del primer arranque: flags desactivados, idle, idempotencia."""
import sys
from pathlib import Path
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_autostart as auto
from lib import constants


FILES = ("/storage/.mnt/videos/1/probe.mkv",
         "/storage/.mnt/tvshows/2/probe.mkv")


class FirstRunTests(unittest.TestCase):
    def config(self, *, enabled=True, feature=True, rollback=True,
               retire=True, recovery=False, known=FILES):
        patches = [
            mock.patch.object(constants, "RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED",
                              enabled),
            mock.patch.object(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                              feature),
            mock.patch.object(constants, "RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED",
                              rollback),
            mock.patch.object(constants,
                              "RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED",
                              retire),
            mock.patch.object(constants,
                              "RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED",
                              recovery),
            mock.patch.object(constants, "RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES",
                              known),
            mock.patch.object(auto.os, "geteuid", return_value=0),
        ]
        return patches

    def run_case(self, mode, *, playback_idle=True, outcome="ACTIVE",
                 cleanup="CLEANED", **flags):
        patches = self.config(**flags)
        with mock.patch.object(auto.rollout, "mode", return_value=mode), \
             mock.patch.object(auto.kodi_idle, "is_playback_idle",
                               return_value=playback_idle), \
             mock.patch.object(auto.live, "execute_with_local_lock",
                               return_value=outcome) as execute, \
             mock.patch.object(auto.live, "recover_with_local_lock",
                               return_value="ROLLED_BACK") as recover, \
             mock.patch.object(auto.cleanup, "retire_after_active",
                               return_value=cleanup) as retire, \
             mock.patch.object(auto.live, "LocalAdapter") as adapter, \
             patches[0], patches[1], patches[2], patches[3], patches[4], \
             patches[5], patches[6]:
            result = auto.tick(lambda _: '{}')
        return result, execute, recover, retire, adapter

    def test_default_disabled_without_any_calls(self):
        with mock.patch.object(auto.rollout, "mode",
                               side_effect=AssertionError("no state")), \
             mock.patch.object(auto.live, "LocalAdapter",
                               side_effect=AssertionError("no IO")):
            self.assertEqual(auto.tick(None), "DISABLED")

    def test_missing_release_feature_gate_refuses(self):
        result, execute, recover, retire, adapter = self.run_case(
            "legacy", feature=False)
        self.assertEqual(result, "BLOCKED_RELEASE_GATES")
        adapter.assert_not_called()
        execute.assert_not_called()

    def test_rollback_gate_must_be_true(self):
        result, _, _, _, adapter = self.run_case("legacy", rollback=False)
        self.assertEqual(result, "BLOCKED_RELEASE_GATES")
        adapter.assert_not_called()

    def test_no_rpc_blocks_before_any_adapter(self):
        flags = self.config()
        with mock.patch.object(auto.live, "LocalAdapter") as adapter, \
             flags[0], flags[1], flags[2], flags[3], flags[4], \
             flags[5], flags[6]:
            self.assertEqual(auto.tick(None), "BLOCKED_KODI_RPC")
            adapter.assert_not_called()

    def test_media_missing_fails_closed_before_touch(self):
        result, _, _, _, adapter = self.run_case("legacy", known=())
        self.assertEqual(result, "BLOCKED_MEDIA_FIXTURES")
        adapter.assert_not_called()

    def test_media_path_escape_or_duplicate_account_blocked(self):
        for values in (
            ("/tmp/a.mkv", FILES[1]),
            ("/storage/.mnt/videos/1/../oops", FILES[1]),
            (FILES[0], FILES[0]),
            (FILES[0], "/storage/.mnt/videos/2/"),
            ("", FILES[1])):
            with self.subTest(values=values):
                self.assertFalse(auto._valid_media_paths(values))

    def test_legacy_active_playback_is_deferred_without_mutation(self):
        result, execute, recover, retire, _ = self.run_case(
            "legacy", playback_idle=False)
        self.assertEqual(result, "DEFERRED_PLAYBACK_ACTIVE")
        execute.assert_not_called()
        recover.assert_not_called()
        retire.assert_not_called()

    def test_idle_legacy_executed_once_and_cleanup_after_active(self):
        result, execute, recover, retire, adapter = self.run_case("legacy")
        self.assertEqual(result, "ACTIVE_VERIFIED_LEGACY_RETIRED")
        execute.assert_called_once()
        retire.assert_called_once()
        recover.assert_not_called()
        self.assertEqual(adapter.call_count, 1)

    def test_rollout_rolled_back_does_not_delete_legacy(self):
        result, _, _, retire, _ = self.run_case(
            "legacy", outcome="ROLLED_BACK")
        self.assertEqual(result, "ROLLED_BACK")
        retire.assert_not_called()

    def test_legacy_active_without_cleanup_flag_keeps_old_files(self):
        result, execute, recover, retire, _ = self.run_case(
            "legacy", retire=False)
        self.assertEqual(result, "ACTIVE_PENDING_CLEANUP")
        execute.assert_called_once()
        retire.assert_not_called()

    def test_active_mode_does_not_repeat_cutover(self):
        result, execute, recover, retire, _ = self.run_case(
            "active", cleanup="ALREADY_CLEAN")
        self.assertEqual(result, "ACTIVE_CLEAN_ALREADY")
        execute.assert_not_called()
        recover.assert_not_called()
        retire.assert_called_once()

    def test_active_resume_partial_cleanup(self):
        result, execute, _, retire, _ = self.run_case("active")
        self.assertEqual(result, "ACTIVE_VERIFIED_LEGACY_RETIRED")
        execute.assert_not_called()
        retire.assert_called_once()

    def test_active_cleanup_failure_keeps_v2(self):
        result, execute, recover, retire, _ = self.run_case(
            "active", cleanup="BLOCKED_CLEANUP_INCOMPLETE")
        self.assertEqual(result, "BLOCKED_CLEANUP_INCOMPLETE")
        execute.assert_not_called()
        recover.assert_not_called()

    def test_prepared_marker_blocks_reentry(self):
        result, execute, recover, retire, adapter = self.run_case("prepared")
        self.assertEqual(result, "BLOCKED_PREPARED_STATE")
        adapter.assert_not_called()

    def test_unknown_mode_blocks(self):
        result, _, _, _, adapter = self.run_case("unexpected")
        self.assertEqual(result, "BLOCKED_UNEXPECTED_MODE")
        adapter.assert_not_called()

    def test_unsafe_requires_recovery_flag(self):
        result, execute, recover, retire, _ = self.run_case(
            "unsafe", recovery=False)
        self.assertEqual(result, "BLOCKED_RECOVERY_NOT_ENABLED")
        execute.assert_not_called()
        recover.assert_not_called()
        retire.assert_not_called()

    def test_unsafe_recovery_only_when_idle_and_flagged(self):
        result, execute, recover, retire, _ = self.run_case(
            "unsafe", recovery=True)
        self.assertEqual(result, "ROLLED_BACK")
        recover.assert_called_once()
        execute.assert_not_called()
        retire.assert_not_called()

    def test_unsafe_playback_does_not_recover(self):
        result, _, recover, _, _ = self.run_case(
            "unsafe", recovery=True, playback_idle=False)
        self.assertEqual(result, "DEFERRED_PLAYBACK_ACTIVE")
        recover.assert_not_called()

    def test_unknown_engine_return_is_not_exposed(self):
        result, _, _, _, _ = self.run_case(
            "legacy", outcome="refresh_token=SENSITIVE")
        self.assertEqual(result, "BLOCKED_MANUAL_RECOVERY_REQUIRED")

    def test_unknown_cleanup_return_is_not_exposed(self):
        result, _, _, _, _ = self.run_case(
            "active", cleanup="SECRET_CONTENT")
        self.assertEqual(result, "BLOCKED_LOCAL_ERROR")

    def test_service_wires_first_run_and_periodic_retry(self):
        service = (Path(__file__).resolve().parents[1] / "service.py").read_text()
        self.assertIn("_rclone_v2_autostart_worker", service)
        self.assertIn("rclone_two_mount_autostart.tick", service)
        self.assertIn("periodic_rclone_v2_cutover", service)


if __name__ == "__main__":
    unittest.main()
