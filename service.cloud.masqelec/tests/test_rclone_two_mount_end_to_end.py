# -*- coding: utf-8 -*-
"""Ensayo de cutover de extremo a extremo SIN systemd ni FUSE real.

Los comandos, montajes y estados son simulados. Los snapshots, journal,
instalación exclusiva, lectura de config, marcadores y rollback se ejecutan
en un árbol temporal real. Nunca accede a OneDrive ni toca KodiELEC.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import constants
from lib import rclone_two_mount_boot_guard as boot
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from test_rclone_mount_isolation import wrapped_conf, sample_units


class FakeSystemd:
    """Modelo de los 4 FUSE originales, 2 FUSE nuevos y 4 bind."""

    def __init__(self):
        self.active = set(rollout.LEGACY_SERVICES)
        self.enabled = set(rollout.LEGACY_SERVICES)
        self.mounts = {}
        self.actions = []
        self.fail_start = set()
        self.on_start = None
        self._mount_legacy()

    def _mount_legacy(self):
        for number, (_, _, _, dst) in enumerate(plan.BIND_MAP):
            self.mounts[dst] = ("0:" + str(50 + number),
                                "/", "fuse.rclone", "old" + str(number))

    def __call__(self, argv):
        self.actions.append(tuple(argv))
        if argv[0] != "systemctl":
            return False
        op = argv[1]
        if op == "is-active":
            return argv[-1] in self.active
        if op == "daemon-reload":
            return True
        unit = argv[2]
        if op == "enable":
            self.enabled.add(unit)
            return True
        if op == "disable":
            self.enabled.discard(unit)
            return True
        if op == "start":
            if unit in self.fail_start:
                return False
            self.active.add(unit)
            if unit in rollout.LEGACY_SERVICES:
                mapping = {
                    "rclone_tvshows_1.service": "/storage/.mnt/tvshows/1",
                    "rclone_tvshows_2.service": "/storage/.mnt/tvshows/2",
                    "rclone_videos_1.service": "/storage/.mnt/videos/1",
                    "rclone_videos_2.service": "/storage/.mnt/videos/2",
                }
                index = list(mapping).index(unit)
                self.mounts[mapping[unit]] = (
                    "0:" + str(50 + index), "/", "fuse.rclone",
                    "old" + str(index))
            elif unit in rollout.NEW_SERVICES:
                index = rollout.NEW_SERVICES.index(unit)
                self.mounts[plan.FUSE_ROOTS[index]] = (
                    "0:" + str(80 + index), "/", "fuse.rclone",
                    "one" + str(index))
            elif unit in rollout.BIND_SERVICES:
                entry = next((v for v in plan.BIND_MAP if v[0] == unit))
                _, index, folder, target = entry
                self.mounts[target] = (
                    "0:" + str(80 + index), "/" + folder,
                    "fuse.rclone", "one" + str(index))
            if self.on_start is not None:
                self.on_start(unit)
            return True
        if op == "stop":
            self.active.discard(unit)
            if unit in rollout.LEGACY_SERVICES:
                # Each legacy FUSE has its own target.
                reverse = {
                    "rclone_tvshows_1.service": "/storage/.mnt/tvshows/1",
                    "rclone_tvshows_2.service": "/storage/.mnt/tvshows/2",
                    "rclone_videos_1.service": "/storage/.mnt/videos/1",
                    "rclone_videos_2.service": "/storage/.mnt/videos/2",
                }
                self.mounts.pop(reverse[unit], None)
            elif unit in rollout.NEW_SERVICES:
                index = rollout.NEW_SERVICES.index(unit)
                self.mounts.pop(plan.FUSE_ROOTS[index], None)
            else:
                target = next(v[3] for v in plan.BIND_MAP if v[0] == unit)
                self.mounts.pop(target, None)
            return True
        return False

    def mountinfo(self):
        result = []
        for number, (path, (dev, root, fs, src)) in enumerate(
                sorted(self.mounts.items()), 100):
            result.append("{} 1 {} {} {} rw - {} {} rw".format(
                number, dev, root, path, fs, src))
        return "\n".join(result)


class IntegratedCutoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(
            prefix="masqelec-end-to-end-", dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.system = FakeSystemd()
        self.units = base / "units"
        self.units.mkdir(mode=0o700)
        for name, content in sample_units().items():
            (self.units / name).write_bytes(content)
        self.conf = base / "canonical.conf"
        self.original = wrapped_conf("crypt")
        self.conf.write_bytes(self.original)
        self.conf.chmod(0o600)
        self.accounts = base / "accounts"
        self.marker = base / "mode.json"
        self.txn_parent = base / "transaction"
        self.adapter = live.LocalAdapter(
            rpc_call=lambda _: '{"jsonrpc":"2.0","id":1,"result":[]}',
            live_enabled=True, canonical=str(self.conf),
            unit_dir=str(self.units),
            account_confs=(
                str(self.accounts / "account1.conf"),
                str(self.accounts / "account2.conf")),
            state_path=str(self.marker),
            txn_parent=str(self.txn_parent),
            runner=self.system, mount_reader=self.system.mountinfo,
            known_media_files=(
                "/storage/.mnt/videos/1/known1.mkv",
                "/storage/.mnt/tvshows/2/known2.mkv"),
        )

    def run_cutover(self):
        with mock.patch.object(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                               True), \
             mock.patch.object(self.adapter, "_probe_known_media",
                               return_value=True):
            return live.execute_with_local_lock(
                self.adapter, authorized=True, verified_rollback=True)

    def test_full_cutover_marks_active_and_keeps_four_kodi_paths(self):
        self.assertEqual(self.run_cutover(), "ACTIVE")
        self.assertEqual(self.system.enabled,
                         set(rollout.NEW_SERVICES + rollout.BIND_SERVICES))
        self.assertEqual(self.system.active,
                         set(rollout.NEW_SERVICES + rollout.BIND_SERVICES))
        self.assertEqual(len(self.system.mounts), 6)
        self.assertTrue(self.adapter.complete_health.__self__ is self.adapter)
        self.assertEqual(journal.phase(self.adapter.txn), "active")
        self.assertEqual(rollout.mode(True, str(self.marker)), "active")
        self.assertFalse(boot.recovery_required(
            parent=str(self.txn_parent), state_path=str(self.marker),
            feature_allowed=True))
        self.assertTrue(self.conf.read_bytes() == self.original)
        self.assertTrue(all(Path(path).stat().st_mode & 0o777 == 0o600
                            for path in self.adapter.account_confs))
        self.assertTrue(all((self.units / n).exists() for n in
                            rollout.NEW_SERVICES + rollout.BIND_SERVICES))
        self.assertTrue(all(target in self.system.mounts
                            for _, _, _, target in plan.BIND_MAP))

    def test_bind_start_failure_rolls_back_and_restores_legacy(self):
        self.system.fail_start.add(rollout.BIND_SERVICES[1])
        self.assertEqual(self.run_cutover(), "ROLLED_BACK")
        self.assertEqual(self.system.active, set(rollout.LEGACY_SERVICES))
        self.assertEqual(self.system.enabled, set(rollout.LEGACY_SERVICES))
        self.assertEqual(len(self.system.mounts), 4)
        self.assertEqual(self.original, self.conf.read_bytes())
        self.assertFalse(self.marker.exists())
        self.assertTrue(all(not (self.units / name).exists()
                            for name in rollout.NEW_SERVICES +
                                        rollout.BIND_SERVICES))
        self.assertTrue(all(not Path(p).exists()
                            for p in self.adapter.account_confs))
        self.assertEqual(journal.phase(self.adapter.txn), "legacy_restored")
        self.assertFalse(boot.recovery_required(
            parent=str(self.txn_parent), state_path=str(self.marker)))

    def test_legacy_stop_failure_rolls_back_without_installing(self):
        def fail_stop(argv):
            if argv[:2] == ["systemctl", "stop"] and (
                    argv[-1] == rollout.LEGACY_SERVICES[1]):
                return False
            return self.system(argv)
        self.adapter.runner = fail_stop
        self.assertEqual(self.run_cutover(), "ROLLED_BACK")
        self.assertFalse(self.marker.exists())
        self.assertEqual(self.system.active, set(rollout.LEGACY_SERVICES))

    def test_failure_in_v2_mount_layout_cannot_be_marked_active(self):
        self.system.fail_start.add(rollout.BIND_SERVICES[2])
        self.assertEqual(self.run_cutover(), "ROLLED_BACK")
        self.assertNotEqual(rollout.mode(True, str(self.marker)), "active")

    def test_legacy_mount_not_restored_even_if_service_reports_active(self):
        self.system.fail_start.add(rollout.BIND_SERVICES[0])
        original = self.system.__call__
        def mounts_missing(argv):
            ok = original(argv)
            if (argv[1] == "start" and
                    argv[2] == rollout.LEGACY_SERVICES[-1]):
                self.system.mounts.pop(
                    "/storage/.mnt/videos/2", None)
            return ok
        self.adapter.runner = mounts_missing
        self.assertEqual(self.run_cutover(), "MANUAL_RECOVERY_REQUIRED")
        self.assertTrue(self.marker.exists())
        self.assertEqual(journal.phase(self.adapter.txn),
                         "rollback_required")
        self.assertTrue(boot.recovery_required(
            parent=str(self.txn_parent), state_path=str(self.marker)))

    def test_refreshed_onedrive_uses_private_legacy_override_no_clobber(self):
        def rotate(unit):
            if unit == rollout.NEW_SERVICES[0]:
                config = self.accounts / "account1.conf"
                old = config.read_bytes()
                updated = old.replace(
                    b"refresh-users_library_1",
                    b"ROTATED_REFRESH_ONEDRIVE_1")
                if old == updated:
                    raise AssertionError("Fixture OAuth token missing")
                config.write_bytes(updated)
        self.system.on_start = rotate
        self.system.fail_start.add(rollout.BIND_SERVICES[1])
        self.assertEqual(self.run_cutover(), "ROLLED_BACK")
        self.assertEqual(self.original, self.conf.read_bytes())
        self.assertEqual(self.system.active, set(rollout.LEGACY_SERVICES))
        self.assertFalse(self.marker.exists())
        self.assertFalse(boot.recovery_required(
            parent=str(self.txn_parent), state_path=str(self.marker),
            unit_dir=str(self.units)))
        self.assertEqual(journal.phase(self.adapter.txn),
                         "legacy_restored")
        recovery = Path(self.adapter.txn, "canonical-recovery-candidate.conf")
        self.assertTrue(recovery.exists())
        self.assertEqual(recovery.stat().st_mode & 0o777, 0o600)
        self.assertIn(b"ROTATED_REFRESH_ONEDRIVE_1",
                      recovery.read_bytes())
        for unit in rollout.LEGACY_SERVICES:
            dropin = self.units / (unit + ".d") / (
                "90-masqelec-oauth-recovery.conf")
            self.assertTrue(dropin.is_file())
            self.assertIn(str(recovery), dropin.read_text())
            self.assertIn(b"--config", dropin.read_bytes())

    def test_crash_after_marker_requires_recovery_without_legacy_restart(self):
        with journal.locked(str(self.txn_parent)):
            self.assertTrue(self.adapter.legacy_preflight())
            self.assertTrue(self.adapter.prepare_durable_rollback())
            self.adapter.mark_cutover_started()
            self.adapter.stop_legacy()
        self.assertFalse(self.system.enabled.intersection(
            set(rollout.LEGACY_SERVICES)))
        self.assertTrue(boot.recovery_required(
            parent=str(self.txn_parent), state_path=str(self.marker)))
        self.assertEqual(len(self.system.mounts), 0)
        self.assertEqual(journal.phase(self.adapter.txn), "cutover_started")
        self.assertEqual(self.original, self.conf.read_bytes())


if __name__ == "__main__":
    unittest.main()
