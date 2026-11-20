# -*- coding: utf-8 -*-
"""Control de arranque tras reboot: solo ficheros /tmp y tests sintéticos."""
import json
import os
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_boot_guard as guard
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_recovery_units as recovery_units
from test_rclone_mount_isolation import wrapped_conf, sample_units


class BootGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name, "journal")
        self.marker = Path(self.temp.name, "state.json")
        self.units = Path(self.temp.name, "system.d")
        self.units.mkdir(mode=0o700)

    def detect(self, **kw):
        return guard.recovery_required(
            parent=str(self.parent), state_path=str(self.marker),
            unit_dir=str(self.units), **kw)

    def prepared(self):
        with journal.locked(str(self.parent)):
            return journal.prepare(str(self.parent),
                                   wrapped_conf("crypt"), sample_units())

    def write_active_marker(self):
        self.marker.write_text(json.dumps({
            "schema": 1, "layout": rollout.LAYOUT,
            "state": "active", "candidate_id": rollout.CANDIDATE_ID,
        }))

    def test_fresh_legacy_no_transaction_allowed(self):
        self.assertFalse(self.detect())

    def test_marker_without_journal_blocks(self):
        self.write_active_marker()
        self.assertTrue(self.detect(feature_allowed=True))

    def test_prepared_without_marker_allows_legacy(self):
        self.prepared()
        self.assertFalse(self.detect())

    def test_prepared_with_marker_blocks(self):
        self.prepared()
        self.marker.write_text("{}")
        self.assertTrue(self.detect())

    def test_crash_started_blocks_even_if_marker_missing(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
        self.assertTrue(self.detect())
        self.write_active_marker()
        self.assertTrue(self.detect(feature_allowed=True))

    def test_crash_rollback_required_blocks(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
            journal.transition(path, "cutover_started", "rollback_required")
        self.assertTrue(self.detect())

    def test_active_with_feature_and_marker_allowed(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
            journal.transition(path, "cutover_started", "active")
        self.write_active_marker()
        self.assertFalse(self.detect(feature_allowed=True))
        self.assertTrue(self.detect(feature_allowed=False))

    def test_active_without_marker_blocks(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
            journal.transition(path, "cutover_started", "active")
        self.assertTrue(self.detect(feature_allowed=True))

    def test_restored_no_marker_allows_legacy(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
            journal.transition(path, "cutover_started", "rollback_required")
            journal.transition(path, "rollback_required", "legacy_restored")
        self.assertFalse(self.detect())

    def test_restored_with_stale_marker_blocks(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
            journal.transition(path, "cutover_started", "rollback_required")
            journal.transition(path, "rollback_required", "legacy_restored")
        self.write_active_marker()
        self.assertTrue(self.detect())

    def test_corrupt_phase_blocks(self):
        target = self.prepared()
        Path(target, "phase.json").write_text("invalid-json")
        self.assertTrue(self.detect())

    def test_symlink_journal_target_blocks(self):
        self.parent.mkdir(mode=0o700)
        (self.parent / rollout.CANDIDATE_ID).symlink_to(self.parent)
        self.assertTrue(self.detect())

    def with_recovery(self):
        target = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(target, "prepared", "cutover_started")
            journal.transition(target, "cutover_started",
                               "rollback_required")
            journal.transition(target, "rollback_required",
                               "legacy_restored")
        file = Path(target, "canonical-recovery-candidate.conf")
        file.write_bytes(wrapped_conf("crypt"))
        file.chmod(0o600)
        overrides = recovery_units.overrides(sample_units(), str(file))
        for name, content in overrides.items():
            directory = self.units / (name + ".d")
            directory.mkdir(mode=0o700)
            dest = directory / recovery_units.DROPIN
            dest.write_bytes(content)
            dest.chmod(0o644)
        return target

    def test_restored_with_private_overrides_allows_legacy(self):
        self.with_recovery()
        self.assertFalse(self.detect())

    def test_rotated_config_without_dropins_blocks(self):
        target = self.with_recovery()
        directory = self.units / (rollout.LEGACY_SERVICES[0] + ".d")
        (directory / recovery_units.DROPIN).unlink()
        self.assertTrue(self.detect())

    def test_rotated_config_mismatch_dropin_blocks(self):
        self.with_recovery()
        directory = self.units / (rollout.LEGACY_SERVICES[1] + ".d")
        (directory / recovery_units.DROPIN).write_bytes(b"wrong")
        self.assertTrue(self.detect())

    def test_rotated_config_unsafe_permissions_block(self):
        target = self.with_recovery()
        Path(target, "canonical-recovery-candidate.conf").chmod(0o644)
        self.assertTrue(self.detect())

    def test_rotated_config_missing_blocks(self):
        target = self.with_recovery()
        Path(target, "canonical-recovery-candidate.conf").unlink()
        self.assertTrue(self.detect())

    def test_partial_overrides_without_candidate_blocks(self):
        target = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(target, "prepared", "cutover_started")
            journal.transition(target, "cutover_started",
                               "rollback_required")
            journal.transition(target, "rollback_required",
                               "legacy_restored")
        (self.units / (rollout.LEGACY_SERVICES[0] + ".d")).mkdir()
        self.assertTrue(self.detect())

    def test_recovery_dir_symlink_blocks(self):
        self.with_recovery()
        directory = self.units / (rollout.LEGACY_SERVICES[0] + ".d")
        real = self.units / "recovery-real"
        directory.rename(real)
        directory.symlink_to(real)
        self.assertTrue(self.detect())

    def test_marker_symlink_blocks_active(self):
        path = self.prepared()
        with journal.locked(str(self.parent)):
            journal.transition(path, "prepared", "cutover_started")
            journal.transition(path, "cutover_started", "active")
        real = Path(self.temp.name, "real")
        real.write_text("{}")
        self.marker.symlink_to(real)
        self.assertTrue(self.detect(feature_allowed=True))


if __name__ == "__main__":
    unittest.main()
