# -*- coding: utf-8 -*-
"""P0-C2: tests sin credenciales ni /proc real."""
import contextlib
import io
import os
from pathlib import Path
import importlib.util
import types
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / (
    "tools/rclone_fleet_inventory_readonly.py")
spec = importlib.util.spec_from_file_location("fleet_inventory_lab", SCRIPT)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class SyntheticProc:
    def __init__(self, processes, *, fail_names=()):
        self._entries = []
        self._cmd = {}
        self._fail_names = set(fail_names)
        for i, process in enumerate(processes):
            ident = str(4000 + i)
            name = "/proc/" + ident + "/cmdline"
            self._entries.append(types.SimpleNamespace(
                name=ident, path="/proc/" + ident))
            self._cmd[name] = (
                process if isinstance(process, bytes) else
                b"\0".join(x.encode("utf-8") for x in process) + b"\0"
            )

    def __iter__(self):
        return iter(self._entries)

    def close(self):
        pass

    def open(self, name, mode):
        if name in self._fail_names:
            raise PermissionError()
        return io.BytesIO(self._cmd[name])


class FleetInventoryReadOnlyTests(unittest.TestCase):
    def scan(self, data, *, fail_names=()):
        fake = SyntheticProc(data, fail_names=fail_names)
        with mock.patch.object(lab.os, "scandir", return_value=fake), \
             mock.patch("builtins.open", side_effect=fake.open), \
             mock.patch.object(lab.os, "getpid", return_value=999999):
            return lab.local_snapshot()

    def test_legacy_four_mounts_classified_without_config_access(self):
        data = self.scan([
            ["rclone", "mount", "users_library_1:movies", "/tmp/a"],
            ["rclone", "mount", "users_library_1:tvshows", "/tmp/b"],
            ["rclone", "mount", "users_library_2:movies", "/tmp/c"],
            ["rclone", "mount", "users_library_2:tvshows", "/tmp/d"],
        ])
        self.assertEqual((data["rclone"], data["mounts"],
                          data["account1"], data["account2"],
                          data["unclassified"]), (4, 4, 2, 2, 0))

    def test_future_two_mounts_classified(self):
        data = self.scan([
            ["/usr/bin/rclone", "--config=/private/file", "mount",
             "users_library_1:", "/storage/.mnt/cloud/1"],
            ["/usr/bin/rclone", "mount", "users_library_2:",
             "/storage/.mnt/cloud/2"],
        ])
        self.assertEqual((data["account1"], data["account2"]), (1, 1))
        self.assertEqual(data["mounts"], 2)

    def test_direct_onedrive_remote_is_also_writer(self):
        data = self.scan([["rclone", "mount", "library_1:movies", "/tmp/a"]])
        self.assertEqual(data["account1"], 1)

    def test_mount_verb_after_many_flags_detected(self):
        flags = ["--global-option-{}".format(x) for x in range(12)]
        data = self.scan([["rclone"] + flags +
                          ["mount", "users_library_2:", "/tmp/a"]])
        self.assertEqual(data["account2"], 1)

    def test_non_mount_rclone_lsf_is_unclassified(self):
        data = self.scan([["rclone", "lsf", "library_1:"]])
        self.assertEqual(data["rclone"], 1)
        self.assertEqual(data["mounts"], 0)
        self.assertEqual(data["unclassified"], 1)

    def test_mount_of_two_accounts_is_ambiguous(self):
        data = self.scan([["rclone", "mount", "users_library_1:",
                           "library_2:", "/tmp/a"]])
        self.assertEqual(data["unclassified"], 1)
        self.assertEqual(data["account1"], 0)
        self.assertEqual(data["account2"], 0)

    def test_unknown_mount_is_unclassified(self):
        data = self.scan([["rclone", "mount", "other:tmp", "/tmp/a"]])
        self.assertEqual(data["unclassified"], 1)

    def test_non_rclone_process_ignored(self):
        data = self.scan([["python3", "rclone", "mount", "library_1:"]])
        self.assertEqual(data["rclone"], 0)

    def test_proc_truncated_fails_to_classify(self):
        data = self.scan([b"rclone\0lsf\0" + b"x" * 20000])
        self.assertEqual(data["unreadable"], 1)
        self.assertEqual(data["rclone"], 0)

    def test_unterminated_cmdline_fails_closed(self):
        data = self.scan([b"rclone\0mount\0library_1:"])
        self.assertEqual(data["unreadable"], 1)

    def test_permission_denied_proc_is_not_safe(self):
        data = self.scan([["rclone", "mount", "library_1:", "/tmp"]],
                         fail_names=("/proc/4000/cmdline",))
        self.assertEqual(data["unreadable"], 1)

    def test_proc_unavailable_blocks(self):
        with mock.patch.object(lab.os, "scandir",
                               side_effect=PermissionError):
            self.assertIsNone(lab.local_snapshot())

    def test_empty_snapshot_still_fleet_blocked(self):
        with mock.patch.object(lab, "local_snapshot", return_value={
                "rclone": 0, "mounts": 0, "account1": 0,
                "account2": 0, "unclassified": 0, "unreadable": 0}), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(lab.main(["--local-readonly"]), 2)
        self.assertIn("REMOTE_CLIENTS_CHECKED=NO", output.getvalue())
        self.assertIn("LAB_RESULT=BLOCKED_FLEET_NOT_VERIFIED",
                      output.getvalue())

    def test_invalid_args_never_scan(self):
        with mock.patch.object(lab, "local_snapshot",
                               side_effect=AssertionError("scan forbidden")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--real-probe"]), 2)
        self.assertIn("LAB_RESULT=BLOCKED_INVALID_MODE", out.getvalue())

    def test_sensitive_argv_never_logged(self):
        fake = {
            "rclone": 1, "mounts": 1, "account1": 1,
            "account2": 0, "unclassified": 0, "unreadable": 0,
        }
        with mock.patch.object(lab, "local_snapshot", return_value=fake), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--local-readonly"]), 2)
        body = out.getvalue()
        for forbidden in ("Authorization:", "token=", "https://",
                          "rclone.conf", "--config=", "password="):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
