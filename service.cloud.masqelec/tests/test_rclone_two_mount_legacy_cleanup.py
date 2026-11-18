# -*- coding: utf-8 -*-
"""Eliminación legacy post-ACTIVE, sin ejecutar systemd ni tocar Kodi real."""
import os
import sys
import tempfile
from pathlib import Path
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_legacy_cleanup as cleanup
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_rollout as rollout
from test_rclone_mount_isolation import wrapped_conf, sample_units


class DummyAdapter:
    def __init__(self, root):
        self.enabled = True
        self.root = Path(root)
        self.unit_dir = str(self.root / "system.d")
        self.txn_parent = str(self.root / "txn")
        self.state_path = str(self.root / "mode.json")
        self.actions = []
        self.good = True
        self.active = set()
        self.enabled_units = set()
        self.fail_reload = False

    def complete_health(self):
        self.actions.append("health")
        return self.good

    def _active(self, unit):
        self.actions.append("active:" + unit)
        return unit in self.active

    def runner(self, args):
        self.actions.append(tuple(args))
        return args[-1] in self.enabled_units

    def _systemctl(self, action):
        self.actions.append("reload")
        if action != "daemon-reload" or self.fail_reload:
            raise RuntimeError("reload failed")


class CleanupTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.a = DummyAdapter(self.root)
        Path(self.a.unit_dir).mkdir()
        Path(self.a.txn_parent).mkdir(mode=0o700)
        self.txn = Path(self.a.txn_parent, rollout.CANDIDATE_ID)
        self.txn.mkdir(mode=0o700)
        for name, original in sample_units().items():
            path = Path(self.a.unit_dir, name)
            path.write_bytes(original)
            path.chmod(0o644)
            backup = self.txn / name
            backup.write_bytes(original)
            backup.chmod(0o600)
        (self.txn / "phase.json").write_bytes(journal._state_bytes("active"))
        (self.txn / "phase.json").chmod(0o600)
        Path(self.a.state_path).write_bytes(
            ('{"schema":1,"layout":"two-fuse-v1","state":"active",'
             '"candidate_id":"2026-11-17-two-fuse-v1"}\n').encode())
        Path(self.a.state_path).chmod(0o600)

    def run_cleanup(self):
        return cleanup.retire_after_active(self.a, authorized=True)

    def test_four_legacy_units_removed_after_active_and_journal_kept(self):
        self.assertEqual(self.run_cleanup(), "CLEANED")
        for unit in rollout.LEGACY_SERVICES:
            self.assertFalse(Path(self.a.unit_dir, unit).exists())
            self.assertTrue(Path(self.txn, unit).exists())
        self.assertEqual(Path(self.txn, cleanup.DONE_NAME).read_bytes(),
                         b"complete\n")
        self.assertEqual(self.a.actions[-1], "reload")

    def test_repeat_cleanup_is_noop(self):
        self.assertEqual(self.run_cleanup(), "CLEANED")
        self.a.actions.clear()
        self.assertEqual(self.run_cleanup(), "ALREADY_CLEAN")
        self.assertEqual(self.a.actions, [])

    def test_not_authorized_does_not_touch_files(self):
        self.assertEqual(cleanup.retire_after_active(self.a),
                         "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(len(list(Path(self.a.unit_dir).iterdir())), 4)
        self.assertEqual(self.a.actions, [])

    def test_operator_disabled_does_not_touch(self):
        self.a.enabled = False
        self.assertEqual(self.run_cleanup(), "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.a.actions, [])

    def test_incomplete_active_mode_blocks(self):
        Path(self.a.state_path).write_text("bad")
        self.assertEqual(self.run_cleanup(), "BLOCKED_NOT_ACTIVE")
        self.assertEqual(self.a.actions, [])

    def test_journal_not_active_blocks(self):
        (self.txn / "phase.json").write_bytes(
            journal._state_bytes("cutover_started"))
        self.assertEqual(self.run_cleanup(), "BLOCKED_JOURNAL_NOT_ACTIVE")
        self.assertTrue(Path(self.a.unit_dir,
                             rollout.LEGACY_SERVICES[0]).exists())

    def test_changed_unit_blocks_all_removals(self):
        name = rollout.LEGACY_SERVICES[-1]
        Path(self.a.unit_dir, name).write_bytes(b"changed\n")
        self.assertEqual(self.run_cleanup(), "BLOCKED_CLEANUP_INCOMPLETE")
        for unit in rollout.LEGACY_SERVICES:
            self.assertTrue(Path(self.a.unit_dir, unit).exists())

    def test_symlink_unit_blocks_all_removals(self):
        path = Path(self.a.unit_dir, rollout.LEGACY_SERVICES[-1])
        path.unlink()
        path.symlink_to(self.txn / rollout.LEGACY_SERVICES[-1])
        self.assertEqual(self.run_cleanup(), "BLOCKED_CLEANUP_INCOMPLETE")
        self.assertTrue(Path(self.a.unit_dir,
                             rollout.LEGACY_SERVICES[0]).exists())

    def test_missing_backup_blocks_all_removals(self):
        (self.txn / rollout.LEGACY_SERVICES[-1]).unlink()
        self.assertEqual(self.run_cleanup(), "BLOCKED_CLEANUP_INCOMPLETE")
        self.assertEqual(len(list(Path(self.a.unit_dir).iterdir())), 4)

    def test_existing_dropin_blocks(self):
        Path(self.a.unit_dir,
             rollout.LEGACY_SERVICES[2] + ".d").mkdir()
        self.assertEqual(self.run_cleanup(), "BLOCKED_LEGACY_DROPINS")
        self.assertEqual(self.a.actions, [])

    def test_unhealthy_v2_blocks(self):
        self.a.good = False
        self.assertEqual(self.run_cleanup(), "BLOCKED_V2_UNHEALTHY")
        self.assertEqual(len(list(Path(self.a.unit_dir).iterdir())), 4)

    def test_legacy_still_running_blocks(self):
        self.a.active.add(rollout.LEGACY_SERVICES[2])
        self.assertEqual(self.run_cleanup(), "BLOCKED_LEGACY_RUNNING")
        self.assertEqual(len(list(Path(self.a.unit_dir).iterdir())), 4)

    def test_legacy_enabled_blocks(self):
        self.a.enabled_units.add(rollout.LEGACY_SERVICES[-1])
        self.assertEqual(self.run_cleanup(), "BLOCKED_LEGACY_ENABLED_OR_UNKNOWN")
        self.assertEqual(len(list(Path(self.a.unit_dir).iterdir())), 4)

    def test_unknown_enabled_state_blocks(self):
        self.a.runner = lambda _: None
        self.assertEqual(self.run_cleanup(), "BLOCKED_LEGACY_ENABLED_OR_UNKNOWN")

    def test_partial_cleanup_resumes_with_same_durable_backup(self):
        name = rollout.LEGACY_SERVICES[0]
        Path(self.a.unit_dir, name).unlink()
        self.assertEqual(self.run_cleanup(), "CLEANED")
        self.assertFalse(any(Path(self.a.unit_dir, n).exists()
                             for n in rollout.LEGACY_SERVICES))

    def test_failed_removal_leaves_cleanup_pending_and_retries(self):
        remove = cleanup.atomic.remove_if_identical
        sequence = [0]
        def sometimes_fail(path, original):
            sequence[0] += 1
            if sequence[0] == 2:
                raise OSError("disk failed")
            return remove(path, original)
        with mock.patch.object(cleanup.atomic, "remove_if_identical",
                               side_effect=sometimes_fail):
            self.assertEqual(self.run_cleanup(), "BLOCKED_CLEANUP_INCOMPLETE")
        self.assertEqual(self.run_cleanup(), "CLEANED")

    def test_daemon_reload_failure_retries_even_after_all_files_removed(self):
        self.a.fail_reload = True
        self.assertEqual(self.run_cleanup(), "BLOCKED_CLEANUP_INCOMPLETE")
        self.assertFalse(Path(self.txn, cleanup.DONE_NAME).exists())
        self.a.fail_reload = False
        self.assertEqual(self.run_cleanup(), "CLEANED")

    def test_done_marker_with_old_unit_is_blocked(self):
        (self.txn / cleanup.DONE_NAME).write_bytes(cleanup.DONE_BYTES)
        (self.txn / cleanup.DONE_NAME).chmod(0o600)
        self.assertEqual(self.run_cleanup(), "BLOCKED_DONE_MARKER_CONFLICT")

    def test_done_marker_tampering_is_blocked(self):
        for name in rollout.LEGACY_SERVICES:
            Path(self.a.unit_dir, name).unlink()
        (self.txn / cleanup.DONE_NAME).write_bytes(b"unknown")
        (self.txn / cleanup.DONE_NAME).chmod(0o600)
        self.assertEqual(self.run_cleanup(), "BLOCKED_DONE_MARKER_CONFLICT")

    def test_account_configs_and_strm_not_touched(self):
        dummy = self.root / "movie.strm"
        dummy.write_text("/storage/.mnt/videos/1/film.mkv")
        canonical = self.root / "rclone.conf"
        canonical.write_bytes(wrapped_conf("crypt"))
        self.assertEqual(self.run_cleanup(), "CLEANED")
        self.assertEqual(dummy.read_text(),
                         "/storage/.mnt/videos/1/film.mkv")
        self.assertEqual(canonical.read_bytes(), wrapped_conf("crypt"))


if __name__ == "__main__":
    unittest.main()
