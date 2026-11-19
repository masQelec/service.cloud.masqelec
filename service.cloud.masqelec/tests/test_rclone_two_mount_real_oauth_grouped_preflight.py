# -*- coding: utf-8 -*-
"""Grouped OAuth pilot preflight is strictly read-only and fail-closed."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock

P = (Path(__file__).resolve().parents[1] /
     "tools/rclone_two_mount_real_oauth_grouped_preflight.py")
SPEC = importlib.util.spec_from_file_location("grouped_oauth_preflight", P)
pilot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pilot)


class GroupedPilotTests(unittest.TestCase):
    def _base(self):
        stack = []
        def patch(obj, name, value):
            context = mock.patch.object(obj, name, value)
            context.start()
            stack.append(context)
        patch(pilot.os, "geteuid", lambda: 0)
        patch(pilot, "ADDON",
              Path("/storage/.kodi/addons/service.cloud.masqelec"))
        patch(pilot, "_regular_private", lambda path: True)
        patch(pilot, "_systemd_value", lambda unit, prop: "active"
              if prop == "ActiveState" else "loaded")
        patch(pilot, "_mount_targets", lambda: set(
            pilot.plan.FUSE_ROOTS +
            tuple(item[3] for item in pilot.plan.BIND_MAP)))
        patch(pilot.rollout, "mode", lambda allowed: "active")
        patch(pilot.guard, "client_recovery_pending", lambda: False)
        for flag in pilot.REAL_FLAGS:
            patch(pilot.constants, flag, False)
        patch(pilot.constants, "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
              False)
        patch(pilot.constants, "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
              False)
        patch(pilot.os.path, "lexists", lambda path: False)
        self.addCleanup(lambda: [p.stop() for p in reversed(stack)])

    def test_invalid_mode_never_reads(self):
        with mock.patch.object(pilot, "inspect",
                               side_effect=AssertionError("unexpected")):
            self.assertEqual(pilot.main(["--activate"]), 2)

    def test_nonroot_stops_before_inspection(self):
        with mock.patch.object(pilot.os, "geteuid", return_value=1000):
            self.assertEqual(pilot.inspect(role="MASTER"),
                             {"PILOT_GATE": "BLOCKED_NOT_ROOT"})

    def test_inactive_layout_blocks(self):
        self._base()
        with mock.patch.object(pilot.rollout, "mode", return_value="legacy"):
            report = pilot.inspect(role="MASTER")
        self.assertEqual(report["PILOT_GATE"],
                         "BLOCKED_V2_LAYOUT_NOT_VERIFIED")

    def test_live_flag_blocks_without_systemd_probe(self):
        self._base()
        with mock.patch.object(pilot.constants,
                               "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                               True), mock.patch.object(
                                   pilot, "_systemd_value",
                                   side_effect=AssertionError("systemd")):
            self.assertEqual(pilot.inspect(role="MASTER")["PILOT_GATE"],
                             "BLOCKED_REAL_FEATURE_FLAGS_ENABLED")

    def test_fake_lab_enabled_blocks(self):
        self._base()
        with mock.patch.object(
                pilot.constants, "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
                True):
            self.assertEqual(pilot.inspect(role="MASTER")["PILOT_GATE"],
                             "BLOCKED_FAKE_LAB_ENABLED")

    def test_master_present_but_no_authorization(self):
        self._base()
        report = pilot.inspect(role="MASTER")
        self.assertEqual(report["PILOT_GATE"],
                         "READONLY_ACTIVE_LAYOUT_PRESENT_NEEDS_OAUTH_GATES")
        self.assertEqual(report["DEV_CLIENT_OVERRIDE"], "OFF")

    def test_untrusted_account_file_blocks(self):
        self._base()
        with mock.patch.object(pilot, "_regular_private",
                               side_effect=lambda p: p != pilot.plan.ACCOUNT_CONFS[1]):
            self.assertEqual(pilot.inspect(role="MASTER")["PILOT_GATE"],
                             "BLOCKED_V2_LAYOUT_NOT_VERIFIED")

    def test_missing_bind_blocks(self):
        self._base()
        with mock.patch.object(pilot, "_mount_targets",
                               return_value=set(pilot.plan.FUSE_ROOTS)):
            self.assertEqual(pilot.inspect(role="MASTER")["PILOT_GATE"],
                             "BLOCKED_V2_LAYOUT_NOT_VERIFIED")

    def test_standalone_role_does_not_import_kodi(self):
        with mock.patch.object(pilot, "_read_role_standalone",
                               return_value="MASTER") as get_role, \
             mock.patch.object(pilot.os, "geteuid", return_value=0), \
             mock.patch.object(pilot, "ADDON",
                               Path("/storage/.kodi/addons/service.cloud.masqelec")), \
             mock.patch.object(pilot.constants,
                               "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
                               True):
            # The role accessor should not be reached if earlier gates fail.
            self.assertEqual(pilot.inspect()["PILOT_GATE"],
                             "BLOCKED_FAKE_LAB_ENABLED")
            get_role.assert_not_called()

    def test_role_reader_fails_closed_without_identity(self):
        with mock.patch.object(pilot, "_literal_master_identity",
                               return_value=("aabbccddeeff", "node")), \
             mock.patch.object(pilot.Path, "read_text",
                               side_effect=OSError("missing eth0")):
            with self.assertRaises(OSError):
                pilot._read_role_standalone()

    def test_importless_role_matches_mac_and_zerotier_node(self):
        with mock.patch.object(pilot, "_literal_master_identity",
                               return_value=("aabbccddeeff", "node-master")), \
             mock.patch.object(pilot.Path, "read_text",
                               return_value="aa:bb:cc:dd:ee:ff"), \
             mock.patch.object(pilot.os.path, "isdir", return_value=True), \
             mock.patch.object(pilot.glob, "glob",
                               return_value=["/tmp/zerotier.conf"]), \
             mock.patch.object(pilot.os.path, "getmtime",
                               return_value=1), \
             mock.patch.object(pilot.os.path, "islink", return_value=False), \
             mock.patch.object(pilot.os.path, "getsize", return_value=48), \
             mock.patch("builtins.open", mock.mock_open(read_data=b"n=node-master\n")):
            self.assertEqual(pilot._read_role_standalone(), "MASTER")

    def test_role_reader_rejects_other_zerotier_node(self):
        with mock.patch.object(pilot, "_literal_master_identity",
                               return_value=("aabbccddeeff", "node-master")), \
             mock.patch.object(pilot.Path, "read_text",
                               return_value="aa:bb:cc:dd:ee:ff"), \
             mock.patch.object(pilot.os.path, "isdir", return_value=True), \
             mock.patch.object(pilot.glob, "glob",
                               return_value=["/tmp/zerotier.conf"]), \
             mock.patch.object(pilot.os.path, "getmtime",
                               return_value=1), \
             mock.patch.object(pilot.os.path, "islink", return_value=False), \
             mock.patch.object(pilot.os.path, "getsize", return_value=48), \
             mock.patch("builtins.open", mock.mock_open(read_data=b"n=other-node\n")):
            self.assertEqual(pilot._read_role_standalone(), "CLIENT")

    def test_role_mismatch_blocks(self):
        self._base()
        self.assertEqual(pilot.inspect(role="CLIENT")["PILOT_GATE"],
                         "BLOCKED_NOT_DEV_MASTER")


if __name__ == "__main__":
    unittest.main()
