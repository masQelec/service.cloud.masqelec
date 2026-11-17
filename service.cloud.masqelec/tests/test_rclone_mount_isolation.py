# -*- coding: utf-8 -*-
"""Laboratorio unitario de aislamiento de 4 rclone mount sin Kodi ni red."""
import json
import os
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import rclone_mount_isolation as iso
from lib import rclone_token_policy as policy


def sample_conf():
    data = []
    for name, kind in (("users_library_1", "onedrive"),
                       ("users_library_2", "onedrive"),
                       ("updater", "drive"), ("logs", "drive")):
        entry = ["[" + name + "]", "type = " + kind,
                 "client_id = isolated-demo"]
        if kind == "onedrive":
            entry += ["drive_id = " + name + "-id",
                      "drive_type = personal"]
        entry.append("token = " + json.dumps({
            "access_token": "access-" + name,
            "refresh_token": "refresh-" + name,
            "expiry": "2026-11-17T09:00:00Z",
        }))
        data.extend(entry + [""])
    data.extend(["[alias]", "type = alias", "remote = users_library_1:", "",
                 "[crypt]", "type = crypt",
                 "remote = users_library_2:secret", "password = opaque", ""])
    return "\n".join(data).encode("utf-8")


def sample_units():
    result = {}
    for service, remote, folder, mountpoint in iso.MOUNT_SPECS:
        result[service] = (
            "[Unit]\nDescription=LAB\n[Service]\n"
            "ExecStart=/storage/.config/rclone/rclone mount "
            + remote + ":" + folder + " " + mountpoint +
            " \\\n  --config /storage/.config/rclone/rclone.conf \\\n"
            "  --read-only \\\n  --buffer-size 16M\n"
        ).encode("utf-8")
    return result


class MountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.config = sample_conf()
        self.units = sample_units()

    def test_layout_exact_two_accounts_four_services(self):
        self.assertEqual(len(iso.MOUNT_SPECS), 4)
        self.assertEqual([r for _, r, _, _ in iso.MOUNT_SPECS].count("users_library_1"), 2)
        self.assertEqual([r for _, r, _, _ in iso.MOUNT_SPECS].count("users_library_2"), 2)
        self.assertTrue(iso.inspect_units(self.units))

    def test_one_process_one_remote_and_no_google_tokens(self):
        for _, remote, _, _ in iso.MOUNT_SPECS:
            raw = iso.select_remote(self.config, remote)
            self.assertEqual(list(policy.oauth_tokens(raw)), [remote])
            self.assertNotIn(b"[updater]", raw)
            self.assertNotIn(b"[logs]", raw)
            self.assertNotIn(b"[crypt]", raw)
            self.assertNotIn(b"[alias]", raw)

    def test_one_account_same_token_in_two_initial_snapshots(self):
        snapshots = {service: iso.select_remote(self.config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        self.assertEqual(iso.account_divergence(snapshots),
                         {"users_library_1": "consistent",
                          "users_library_2": "consistent"})

    def test_divergent_refresh_tokens_not_silently_merged(self):
        snapshots = {service: iso.select_remote(self.config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        snapshots["rclone_videos_1.service"] = snapshots[
            "rclone_videos_1.service"].replace(b"refresh-users_library_1",
                                                b"other-refresh")
        status = iso.account_divergence(snapshots)
        self.assertEqual(status["users_library_1"], "diverged")
        self.assertEqual(status["users_library_2"], "consistent")

    def test_changed_onedrive_identity_blocks_reconciliation(self):
        snapshots = {service: iso.select_remote(self.config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        snapshots["rclone_videos_2.service"] = snapshots[
            "rclone_videos_2.service"].replace(b"drive_type = personal",
                                                b"drive_type = business")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            iso.account_divergence(snapshots)

    def test_unit_proposals_contain_unique_paths(self):
        paths = []
        for unit, _remote, _folder, _mount in iso.MOUNT_SPECS:
            proposed = iso.propose_unit(unit, self.units[unit])
            args = iso._start_args(proposed)
            new_path = iso.proposed_config_path(unit)
            paths.append(new_path)
            self.assertEqual(iso._config_arg(args), new_path)
            self.assertIn(b"--read-only", proposed)
            self.assertNotIn(b"--config /storage/.config/rclone/rclone.conf",
                             proposed)
        self.assertEqual(len(set(paths)), 4)

    def test_plan_rejects_unexpected_mount_remote(self):
        units = dict(self.units)
        units["rclone_videos_2.service"] = units[
            "rclone_videos_2.service"].replace(b"users_library_2:movies",
                                                b"users_library_1:movies")
        with self.assertRaisesRegex(ValueError, "Destino o fuente"):
            iso.inspect_units(units)

    def test_plan_rejects_unknown_service_and_modified_config_path(self):
        with self.assertRaises(ValueError):
            iso.proposed_config_path("unknown.service")
        units = dict(self.units)
        units["rclone_videos_1.service"] = units[
            "rclone_videos_1.service"].replace(
                b"--config /storage/.config/rclone/rclone.conf",
                b"--config /tmp/wrong.conf")
        with self.assertRaisesRegex(ValueError, "configuración inesperada"):
            iso.inspect_units(units)

    def test_stage_proposals_only_in_private_temporary_directory(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o700)
            self.assertEqual(iso.stage_in_directory(root, self.config, self.units), 4)
            self.assertEqual(len(os.listdir(root)), 8)
            for filename in os.listdir(root):
                path = os.path.join(root, filename)
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "vacío"):
                iso.stage_in_directory(root, self.config, self.units)

    def test_stage_rejects_insecure_or_outside_directory(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o755)
            with self.assertRaisesRegex(ValueError, "0700"):
                iso.stage_in_directory(root, self.config, self.units)

    def test_select_remote_rejects_missing_token(self):
        broken = self.config.replace(b"refresh-users_library_1", b"")
        with self.assertRaises(ValueError):
            iso.select_remote(broken, "users_library_1")

    def test_stage_keeps_original_config_and_units_unmodified(self):
        original = bytes(self.config)
        old_units = dict(self.units)
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o700)
            iso.stage_in_directory(root, self.config, self.units)
        self.assertEqual(self.config, original)
        self.assertEqual(self.units, old_units)


if __name__ == "__main__":
    unittest.main()
