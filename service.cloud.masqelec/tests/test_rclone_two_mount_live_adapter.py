# -*- coding: utf-8 -*-
"""Adaptador local opcional: pruebas de guardas, sin acceso systemd real."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_journal as journal
from test_rclone_mount_isolation import wrapped_conf, sample_units


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        root = Path(self.root.name)
        self.units = root / "system.d"
        self.units.mkdir()
        self.config = root / "rclone.conf"
        self.config.write_bytes(wrapped_conf("crypt"))
        self.config.chmod(0o600)
        for name, data in sample_units().items():
            (self.units / name).write_bytes(data)
        self.txn = root / "txn"
        self.marker = root / "mount-mode.json"
        self.accounts = root / "accounts"
        self.actions = []
        self.mountinfo = self.legacy_mountinfo()
        self.adapter = live.LocalAdapter(
            rpc_call=lambda _: '{"jsonrpc":"2.0","id":1,"result":[]}',
            live_enabled=True, canonical=str(self.config),
            unit_dir=str(self.units),
            account_confs=(str(self.accounts / "account1.conf"),
                           str(self.accounts / "account2.conf")),
            state_path=str(self.marker), txn_parent=str(self.txn),
            runner=self.command, mount_reader=lambda:self.mountinfo)

    @staticmethod
    def legacy_mountinfo():
        rows = []
        for k, (_name, _, _, target) in enumerate(
                (("a",1,"movies","/storage/.mnt/videos/1"),
                 ("b",2,"movies","/storage/.mnt/videos/2"),
                 ("c",1,"tvshows","/storage/.mnt/tvshows/1"),
                 ("d",2,"tvshows","/storage/.mnt/tvshows/2"))):
            rows.append("1 0 0:{} / {} rw - fuse.rclone old rw".format(
                30+k, target))
        return "\n".join(rows)

    def command(self, args):
        self.actions.append(tuple(args))
        return True

    def test_disabled_operator_refuses_any_io(self):
        self.adapter.enabled = False
        self.assertEqual(live.execute_with_local_lock(
            self.adapter, authorized=True, verified_rollback=True),
            "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.actions, [])
        self.assertFalse(self.txn.exists())

    def test_no_authorization_refuses(self):
        self.assertEqual(live.execute_with_local_lock(self.adapter),
                         "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.actions, [])

    def test_rollback_gate_refuses(self):
        self.assertEqual(live.execute_with_local_lock(
            self.adapter, authorized=True), "BLOCKED_ROLLBACK_NOT_READY")
        self.assertEqual(self.actions, [])

    def test_legacy_preflight_and_private_prepare(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
        self.assertTrue(Path(self.adapter.txn, "canonical.conf").exists())
        self.assertEqual(journal.phase(self.adapter.txn), "prepared")

    def test_preflight_refuses_existing_v2_unit(self):
        (self.units / rollout.NEW_SERVICES[0]).write_bytes(b"[Unit]\n")
        self.assertFalse(self.adapter.legacy_preflight())

    def test_preflight_refuses_existing_account_config(self):
        self.accounts.mkdir()
        (self.accounts / "account1.conf").write_bytes(b"old")
        self.assertFalse(self.adapter.legacy_preflight())

    def test_preflight_refuses_existing_marker(self):
        self.marker.write_text("{}")
        self.assertFalse(self.adapter.legacy_preflight())

    def test_marker_is_unsafe_before_stopping_legacy(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            self.adapter.mark_cutover_started()
        self.assertEqual(journal.phase(self.adapter.txn),
                         "cutover_started")
        self.assertEqual(rollout.mode(False, str(self.marker)), "unsafe")
        self.assertEqual(self.actions, [])

    def test_mount_guard_identifies_old_and_new(self):
        self.assertTrue(self.adapter._old_mounted())
        self.assertTrue(self.adapter.new_fully_unmounted())
        self.mountinfo += (
            "\n20 1 0:9 / /storage/.mnt/cloud/1 rw - fuse.rclone new rw")
        self.assertFalse(self.adapter.new_fully_unmounted())

    def test_mount_guard_detects_v2_bind_in_old_target(self):
        self.mountinfo = (
            "20 1 0:8 /movies /storage/.mnt/videos/1 rw "
            "- fuse.rclone new rw")
        self.assertFalse(self.adapter.new_fully_unmounted())

    def test_kodi_playback_must_be_empty(self):
        self.assertTrue(self.adapter.playback_still_idle())
        self.adapter.rpc = lambda _: '{"jsonrpc":"2.0","id":1,"result":[{"playerid":1,"type":"video"}]}'
        self.assertFalse(self.adapter.playback_still_idle())

    def test_known_systemctl_commands_only(self):
        with self.assertRaises(ValueError):
            self.adapter._systemctl("restart","rclone_videos_1.service")
        with self.assertRaises(ValueError):
            self.adapter._systemctl("stop","other.service")
        self.assertEqual(self.actions, [])

    def test_real_apply_is_not_exposed_from_addon_service(self):
        src = (Path(__file__).resolve().parents[1] /
               "service.py").read_text()
        self.assertNotIn("rclone_two_mount_live_adapter", src)


if __name__ == "__main__":
    unittest.main()
