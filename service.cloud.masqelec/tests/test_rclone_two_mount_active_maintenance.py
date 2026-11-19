# -*- coding: utf-8 -*-
"""Synthetic active-mode maintenance. Never start two mount layers at one path."""
from contextlib import nullcontext
import sys
from pathlib import Path
import unittest
from unittest import mock
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_active_maintenance as keep
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_plan as plan


class ActiveMountMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.active = set(rollout.NEW_SERVICES + rollout.BIND_SERVICES)
        self.mounts = {}
        for i, root in enumerate(plan.FUSE_ROOTS):
            self.mounts[root] = {"fstype": "fuse.rclone",
                                 "fsroot": "/", "source": "rclone",
                                 "device": "0:{}".format(i)}
        for name, index, folder, destination in plan.BIND_MAP:
            self.mounts[destination] = {
                **self.mounts[plan.FUSE_ROOTS[index]],
                "fsroot": "/" + folder
            }
        self.adapter = SimpleNamespace(enabled=True,
            txn_parent="/fake/txn", state_path="/fake/state",
            unit_dir="/fake/system.d",
            account_confs=("/fake/a1", "/fake/a2"),
            _active=lambda u: u in self.active,
            _mounts=lambda: dict(self.mounts),
            mount_reader=lambda: "synthetic",
            _systemctl=self.start)

    def start(self, operation, unit):
        self.assertEqual(operation, "start")
        self.actions.append(unit)
        self.active.add(unit)
        if unit in rollout.NEW_SERVICES:
            idx = rollout.NEW_SERVICES.index(unit)
            self.mounts[plan.FUSE_ROOTS[idx]] = {
                "fstype":"fuse.rclone", "fsroot":"/",
                "source":"rclone", "device":"0:{}".format(idx)}
        else:
            entry = next(item for item in plan.BIND_MAP if item[0] == unit)
            root = self.mounts[plan.FUSE_ROOTS[entry[1]]]
            self.mounts[entry[3]] = {**root, "fsroot":"/"+entry[2]}

    def run_gate(self, authorized=True):
        with mock.patch.object(keep.rollout, "mode", return_value="active"), \
             mock.patch.object(keep.journal, "phase", return_value="active"), \
             mock.patch.object(keep.journal, "locked", return_value=nullcontext()), \
             mock.patch.object(keep, "_safe_artifacts"), \
             mock.patch.object(keep.health, "check_two_fuse_four_bind",
                               side_effect=lambda _: len(self.mounts) == 6):
            return keep.ensure_active(self.adapter, authorized=authorized)

    def test_healthy_v2_not_restarted(self):
        self.assertEqual(self.run_gate(), "ACTIVE_HEALTHY")
        self.assertEqual(self.actions, [])

    def test_missing_bind_starts_only_that_unit(self):
        unit, _, _, dest = plan.BIND_MAP[0]
        self.active.remove(unit)
        del self.mounts[dest]
        self.assertEqual(self.run_gate(), "ACTIVE_REPAIRED")
        self.assertEqual(self.actions, [unit])

    def test_missing_root_and_bind_repaired_in_order(self):
        rootunit = rollout.NEW_SERVICES[0]
        rootpath = plan.FUSE_ROOTS[0]
        self.active.remove(rootunit)
        del self.mounts[rootpath]
        missing = [item for item in plan.BIND_MAP if item[1] == 0]
        for unit, _, _, dest in missing:
            self.active.remove(unit)
            del self.mounts[dest]
        self.assertEqual(self.run_gate(), "ACTIVE_REPAIRED")
        self.assertEqual(self.actions, [rootunit] + [a[0] for a in missing])

    def test_occupied_root_never_started(self):
        self.active.remove(rollout.NEW_SERVICES[0])
        self.assertEqual(self.run_gate(), "BLOCKED_ROOT_OCCUPIED")
        self.assertEqual(self.actions, [])

    def test_occupied_bind_never_started(self):
        unit = plan.BIND_MAP[0][0]
        self.active.remove(unit)
        self.assertEqual(self.run_gate(), "BLOCKED_BIND_OCCUPIED")
        self.assertEqual(self.actions, [])

    def test_legacy_running_denies_all_starts(self):
        self.active.add(rollout.LEGACY_SERVICES[0])
        self.assertEqual(self.run_gate(), "BLOCKED_LEGACY_RUNNING")
        self.assertEqual(self.actions, [])

    def test_legacy_fuse_on_kodi_path_denied(self):
        target = plan.BIND_MAP[0][3]
        self.mounts[target]["fsroot"] = "/"
        self.assertEqual(self.run_gate(), "BLOCKED_LEGACY_MOUNT")

    def test_unapproved_denies_without_lock(self):
        with mock.patch.object(keep.journal, "locked",
                               side_effect=AssertionError("no lock")):
            self.assertEqual(self.run_gate(authorized=False),
                             "BLOCKED_NOT_AUTHORIZED")

    def test_active_marker_corrupt_refuses(self):
        with mock.patch.object(keep.rollout, "mode", return_value="unsafe"), \
             mock.patch.object(keep.journal, "locked",
                               return_value=nullcontext()):
            self.assertEqual(keep.ensure_active(self.adapter, authorized=True),
                             "BLOCKED_NOT_ACTIVE")


if __name__ == "__main__":
    unittest.main()
