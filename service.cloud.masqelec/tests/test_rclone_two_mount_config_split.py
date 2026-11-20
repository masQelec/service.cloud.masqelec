# -*- coding: utf-8 -*-
"""General rclone config separation: no network, real OAuth or systemd."""
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

from lib import rclone_two_mount_config_split as split
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_startup_stage as stage
from lib import rclone_token_policy as policy
from lib import rclone_mount_isolation as isolation
from test_rclone_mount_isolation import wrapped_conf


def fixture():
    full = wrapped_conf("crypt") + (
        b"\n[masqelec]\ntype = alias\nremote = updater:data\n"
        b"\n[log]\ntype = alias\nremote = logs:logs\n")
    accounts = (plan.account_snapshot(full, 0),
                plan.account_snapshot(full, 1))
    return full, accounts


class ConfigSplitTests(unittest.TestCase):
    def test_general_contains_only_non_onedrive_and_preserves_drive(self):
        full, accounts = fixture()
        general = split.general_only(full, accounts)
        names = policy.sections(general)
        self.assertIn("updater", names)
        self.assertIn("logs", names)
        self.assertIn("masqelec", names)
        self.assertIn("log", names)
        self.assertNotIn("one_a", names)
        self.assertNotIn("one_b", names)
        self.assertNotIn("users_library_1", names)
        self.assertNotIn("users_library_2", names)
        self.assertEqual(set(policy.oauth_tokens(general)),
                         {"updater", "logs"})
        self.assertEqual(split.general_only(general, accounts), general)

    def test_virtual_full_uses_current_isolated_refresh_tokens(self):
        full, accounts = fixture()
        general = split.general_only(full, accounts)
        fresh = accounts[0].replace(b"refresh-users_library_1", b"current-one-a")
        virtual = split.full_view(general, (fresh, accounts[1]))
        policy.validate_master_layout(virtual)
        self.assertIn(b"current-one-a", virtual)
        self.assertNotIn(b"refresh-users_library_1", virtual)
        self.assertEqual(plan.account_snapshot(virtual, 0), fresh)
        self.assertEqual(plan.account_snapshot(virtual, 1), accounts[1])

    def test_virtual_full_accepts_existing_legacy_canonical(self):
        full, accounts = fixture()
        renewed = accounts[1].replace(
            b"refresh-users_library_2", b"rotated-one-b")
        virtual = split.full_view(full, (accounts[0], renewed))
        self.assertIn(b"rotated-one-b", virtual)
        self.assertNotIn(b"refresh-users_library_2", virtual)
        self.assertEqual(split.general_only(virtual, (accounts[0], renewed)),
                         split.general_only(full, accounts))

    def test_changed_static_identity_never_erased(self):
        full, accounts = fixture()
        wrong = accounts[0].replace(b"drive_type = personal",
                                    b"drive_type = business")
        with self.assertRaises(ValueError):
            split.general_only(full, (wrong, accounts[1]))

    def test_unknown_onedrive_is_rejected(self):
        full, accounts = fixture()
        extra = (b"\n[unknown]\ntype = onedrive\n"
                 b"drive_id = x\ndrive_type = personal\n"
                 b"token = {}\n")
        with self.assertRaises(ValueError):
            split.general_only(full + extra, accounts)

    def test_malformed_or_swapped_accounts_are_denied(self):
        full, accounts = fixture()
        for bad in ((accounts[1], accounts[0]),
                    (accounts[0], accounts[0]),
                    (accounts[0], b"corrupted")):
            with self.subTest():
                with self.assertRaises((ValueError, TypeError)):
                    split.full_view(full, bad)

    def test_no_cleanup_without_explicit_verified_gate(self):
        self.assertEqual(split.retire_once(), "BLOCKED_NOT_VERIFIED")
        with mock.patch.object(split.rollout, "mode", return_value="legacy"):
            self.assertEqual(split.retire_once(
                authorized=True, health_verified=True),
                "BLOCKED_NOT_ACTIVE")

    def test_atomic_general_cleanup_and_repeated_read_work(self):
        full, accounts = fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / "rclone.conf"
            config.write_bytes(full)
            config.chmod(0o600)
            isolated = root / "isolated-mounts"
            isolated.mkdir(mode=0o700)
            paths = (isolated / "account1.conf",
                     isolated / "account2.conf")
            for path, account in zip(paths, accounts):
                path.write_bytes(account)
                path.chmod(0o600)
            before_accounts = tuple(path.read_bytes() for path in paths)
            with mock.patch.object(stage, "LOCAL_CONF", str(config)), \
                 mock.patch.object(plan, "ACCOUNT_CONFS",
                                   tuple(map(str, paths))), \
                 mock.patch.object(split, "_is_root", return_value=True), \
                 mock.patch.object(split.rollout, "mode",
                                   return_value="active"):
                self.assertEqual(split.retire_once(
                    authorized=True, health_verified=True), "CLEANED")
                self.assertEqual(split.retire_once(
                    authorized=True, health_verified=True), "ALREADY_CLEAN")
                merged, read_accounts = split.local_sources()
            self.assertEqual(tuple(path.read_bytes() for path in paths),
                             before_accounts)
            self.assertEqual(read_accounts, accounts)
            self.assertEqual(policy.oauth_provider_counts(merged),
                             {"drive": 2, "onedrive": 2})
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
            self.assertNotIn(b"[one_a]", config.read_bytes())
            self.assertIn(b"[masqelec]", config.read_bytes())

    def test_unsafe_account_prevents_cleanup(self):
        full, accounts = fixture()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            config = root / "rclone.conf"
            config.write_bytes(full)
            config.chmod(0o600)
            isolated = root / "isolated-mounts"
            isolated.mkdir(mode=0o700)
            paths = (isolated / "account1.conf",
                     isolated / "account2.conf")
            for path, account in zip(paths, accounts):
                path.write_bytes(account)
                path.chmod(0o644)
            with mock.patch.object(stage, "LOCAL_CONF", str(config)), \
                 mock.patch.object(plan, "ACCOUNT_CONFS",
                                   tuple(map(str, paths))), \
                 mock.patch.object(split, "_is_root", return_value=True), \
                 mock.patch.object(split.rollout, "mode",
                                   return_value="active"):
                # Actual cleanup must refuse unsafe account files.
                self.assertEqual(split.retire_once(
                    authorized=True, health_verified=True),
                    "BLOCKED_INPUT")
            self.assertEqual(config.read_bytes(), full)


if __name__ == "__main__":
    unittest.main()
