# -*- coding: utf-8 -*-
"""Early boot recovery is opt-in and impossible with a running Kodi."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_early_boot_recovery as boot
from lib import rclone_two_mount_rollout as rollout


class EarlyBootRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.parent = self.root / "transaction"
        self.marker = self.root / "marker.json"

    def run_gate(self, **kw):
        params = dict(authorized=True, rollback_verified=True,
                      proc_root=str(self.proc), txn_parent=str(self.parent),
                      state_path=str(self.marker))
        params.update(kw)
        with mock.patch.object(boot.constants,
                               "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", True), \
             mock.patch.object(boot.os, "geteuid", return_value=0):
            return boot.execute(**params)

    def test_default_denies_without_io(self):
        with mock.patch.object(boot, "interrupted_state",
                               side_effect=AssertionError("must not access")):
            self.assertEqual(boot.execute(), "BLOCKED_NOT_AUTHORIZED")

    def test_no_pending_does_not_create_directories(self):
        self.assertEqual(self.run_gate(), "NO_PENDING")
        self.assertFalse(self.parent.exists())
        self.assertFalse(self.marker.exists())

    def test_orphan_marker_blocks(self):
        self.marker.write_text("{}")
        self.assertEqual(self.run_gate(), "BLOCKED_INCONSISTENT_STATE")

    def test_orphan_journal_blocks(self):
        (self.parent / rollout.CANDIDATE_ID).mkdir(parents=True)
        self.assertEqual(self.run_gate(), "BLOCKED_INCONSISTENT_STATE")

    def test_active_marker_never_recovers(self):
        with mock.patch.object(boot, "interrupted_state",
                               return_value="ACTIVE_NO_RECOVERY"), \
             mock.patch.object(boot, "kodi_process_absent",
                               side_effect=AssertionError("unexpected")):
            self.assertEqual(self.run_gate(), "ACTIVE_NO_RECOVERY")

    def test_interrupted_state_requires_exact_unsafe_marker(self):
        txn = self.parent / rollout.CANDIDATE_ID
        txn.mkdir(parents=True)
        with mock.patch.object(boot.journal, "phase",
                               return_value="cutover_started"), \
             mock.patch.object(boot.rollout, "mode", return_value="active"):
            self.marker.write_text("{}")
            self.assertEqual(boot.interrupted_state(
                str(self.parent), str(self.marker)), "BLOCKED_INCONSISTENT_STATE")

    def test_running_kodi_process_blocks(self):
        pid = self.proc / "123"
        pid.mkdir()
        (pid / "comm").write_text("kodi.bin\n")
        (pid / "cmdline").write_bytes(b"/usr/lib/kodi/kodi.bin\x00")
        with mock.patch.object(boot, "interrupted_state",
                               return_value="INTERRUPTED"):
            self.assertEqual(self.run_gate(), "BLOCKED_KODI_RUNNING_OR_UNKNOWN")

    def test_unknown_proc_inventory_blocks(self):
        with mock.patch.object(boot, "interrupted_state",
                               return_value="INTERRUPTED"):
            self.assertEqual(self.run_gate(proc_root=str(self.root / "missing")),
                             "BLOCKED_KODI_RUNNING_OR_UNKNOWN")

    def test_no_kodi_process(self):
        pid = self.proc / "3"
        pid.mkdir()
        (pid / "comm").write_text("systemd\n")
        (pid / "cmdline").write_bytes(b"/sbin/init\x00")
        self.assertTrue(boot.kodi_process_absent(str(self.proc)))

    def test_recovery_requires_recheck_and_locked_journal(self):
        calls = []
        class FakeAdapter:
            txn_parent = str(self.parent)
            def __init__(inner, **kwargs):
                self.assertTrue(kwargs["live_enabled"])
                self.assertEqual(kwargs["known_media_files"], ())
            def recover_pending_from_disk(inner):
                calls.append("recover")
                return "ROLLED_BACK"
        # Mock lock because the test does not supply real journal artifacts.
        from contextlib import contextmanager
        @contextmanager
        def locked(_parent):
            calls.append("lock")
            yield
        with mock.patch.object(boot, "interrupted_state",
                               return_value="INTERRUPTED"), \
             mock.patch.object(boot.journal, "locked", side_effect=locked):
            self.assertEqual(self.run_gate(adapter_factory=FakeAdapter),
                             "ROLLED_BACK")
        self.assertEqual(calls, ["lock", "recover"])

    def test_recovery_failure_fail_closed(self):
        class BadAdapter:
            txn_parent = str(self.parent)
            def __init__(inner, **kwargs):
                pass
            def recover_pending_from_disk(inner):
                raise RuntimeError("synthetic")
        from contextlib import nullcontext
        with mock.patch.object(boot, "interrupted_state",
                               return_value="INTERRUPTED"), \
             mock.patch.object(boot.journal, "locked",
                               return_value=nullcontext()):
            self.assertEqual(self.run_gate(adapter_factory=BadAdapter),
                             "MANUAL_RECOVERY_REQUIRED")

    def test_recovery_gate_refuses_feature_off(self):
        with mock.patch.object(boot.constants,
                               "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False):
            self.assertEqual(boot.execute(authorized=True,
                rollback_verified=True), "BLOCKED_FEATURE_DISABLED")


if __name__ == "__main__":
    unittest.main()
