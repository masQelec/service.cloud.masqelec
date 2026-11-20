# -*- coding: utf-8 -*-
"""No physical mounts: synthetic rollback path with real temporary file IO."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

FILE = Path(__file__).resolve().parents[1] / "tools" / "rclone_two_mount_systemd_local_lab.py"
SPEC = importlib.util.spec_from_file_location("masqelec_fake_rollback", FILE)
lab = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lab)


class FakeRollbackTests(unittest.TestCase):
    def setUp(self):
        self.root = Path("/tmp/masqelec-sd-lab-" + "b" * 16)
        if self.root.exists():
            self.skipTest("Reserved lab fixture already exists; never overwrite")
        self.root.mkdir(mode=0o700)
        self.addCleanup(lambda: shutil.rmtree(self.root))
        self.events = []
        self.names = lab._unit_names(self.root)
        self.fuse, self.binds, self.fixtures = lab._layout(self.root)
        self.stopped = False
        self.fail_other = False
        self.fail_restart = False

    def control(self, action, unit):
        self.events.append((action, unit))
        if action == "start" and self.fail_restart and unit == self.names["fuse"][0]:
            return False
        if unit == self.names["fuse"][0] and action in ("stop", "start"):
            self.stopped = action == "stop"
        return True

    def records(self, data):
        if self.stopped:
            return {}
        return {self.fuse[0]: [{"fstype": "fuse.rclone"}]}

    def active(self, unit):
        return not self.fail_other

    def run_one(self):
        with mock.patch.object(lab, "_control", side_effect=self.control), \
             mock.patch.object(lab, "_is_active", side_effect=self.active), \
             mock.patch.object(lab, "_read_mountinfo", return_value="fixture"), \
             mock.patch.object(lab, "_mount_records", side_effect=self.records), \
             mock.patch.object(lab, "_read_sample", return_value=True), \
             mock.patch.object(lab, "_check_mounts", return_value=True):
            return lab._transaction_account1(self.root)

    def test_rollback_restores_original_bytes_and_account_two_never_stops(self):
        self.assertEqual(self.run_one(),
                         "PASS_REAL_SYSTEMD_FAKE_OAUTH_ROLLBACK_ISOLATED")
        work = self.root / "oauth-lab"
        self.assertEqual((work / "account1.conf").read_bytes(),
                         (work / "account1.bak").read_bytes())
        self.assertEqual((work / "state").read_bytes(), b"rolled_back_verified")
        self.assertFalse(any(unit in (self.names["fuse"][1],
                                      self.names["bind"][1],
                                      self.names["bind"][3])
                             for _, unit in self.events))

    def test_account_two_failure_blocks_credential_install(self):
        self.fail_other = True
        self.assertEqual(self.run_one(), "FAIL_FAKE_OTHER_INTERRUPTED")
        work = self.root / "oauth-lab"
        self.assertEqual((work / "account1.conf").read_bytes(),
                         (work / "account1.bak").read_bytes())

    def test_restart_failure_never_claims_rollback_success(self):
        self.fail_restart = True
        self.assertEqual(self.run_one(), "FAIL_FAKE_START")
        self.assertNotEqual((self.root / "oauth-lab" / "state").read_bytes(),
                            b"rolled_back_verified")

    def test_requires_confirmation(self):
        with mock.patch.object(lab, "run_isolated",
                               side_effect=AssertionError("must not start")):
            self.assertEqual(lab.main(["--fake-oauth-rollback-isolated"]), 2)


if __name__ == "__main__":
    unittest.main()
