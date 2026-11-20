# -*- coding: utf-8 -*-
"""Isolated systemd account cycling protocol, no real mounts/systemctl."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "rclone_two_mount_systemd_local_lab.py"
SPEC = importlib.util.spec_from_file_location("masqelec_cycle_lab", SOURCE)
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


class CycleAccountTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.root = Path("/tmp/masqelec-sd-lab-" + "a" * 16)
        self.names = lab._unit_names(self.root)
        self.fuse, self.binds, _ = lab._layout(self.root)

    def cycle(self, *, interrupt_other=False, stale_mount=False,
              restart_failure=False):
        def ctl(op, unit):
            self.actions.append((op, unit))
            return not (restart_failure and op == "start" and
                        unit == self.names["fuse"][0])
        def active(unit):
            return not (interrupt_other and unit == self.names["fuse"][1])
        def records(raw):
            if stale_mount:
                return {self.fuse[0]: [{}]}
            return {}
        with mock.patch.object(lab, "_control", side_effect=ctl), \
             mock.patch.object(lab, "_is_active", side_effect=active), \
             mock.patch.object(lab, "_read_mountinfo", return_value="mock"), \
             mock.patch.object(lab, "_mount_records", side_effect=records), \
             mock.patch.object(lab, "_read_sample", return_value=True), \
             mock.patch.object(lab, "_check_mounts", return_value=True):
            return lab._cycle_first_account(self.root)

    def test_account_one_only_cycle(self):
        self.assertEqual(self.cycle(),
                         "PASS_REAL_SYSTEMD_ONE_ACCOUNT_RESTART_ISOLATED")
        affected = {unit for operation, unit in self.actions}
        self.assertEqual(affected, {self.names["fuse"][0],
                                    self.names["bind"][0],
                                    self.names["bind"][2]})
        self.assertEqual(self.actions[:3], [
            ("stop", self.names["bind"][2]),
            ("stop", self.names["bind"][0]),
            ("stop", self.names["fuse"][0])])

    def test_stale_mount_blocks_restart(self):
        self.assertEqual(self.cycle(stale_mount=True),
                         "FAIL_ACCOUNT1_NOT_UNMOUNTED")
        self.assertFalse(any(action == "start" for action, _ in self.actions))

    def test_account_two_interruption_blocks_restart(self):
        self.assertEqual(self.cycle(interrupt_other=True),
                         "FAIL_ACCOUNT2_INTERRUPTED")
        self.assertFalse(any(action == "start" for action, _ in self.actions))

    def test_failed_root_restart_detected(self):
        self.assertEqual(self.cycle(restart_failure=True),
                         "FAIL_ACCOUNT1_FUSE_RESTART")

    def test_arguments_deny_unconfirmed_mode(self):
        with mock.patch.object(lab, "run_isolated", side_effect=AssertionError):
            self.assertEqual(lab.main(["--cycle-account1-isolated"]), 2)


if __name__ == "__main__":
    unittest.main()
