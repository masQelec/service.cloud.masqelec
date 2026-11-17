# -*- coding: utf-8 -*-
"""Fences de proceso en laboratorio OAuth v2 sin red ni claves reales."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

SCRIPT = (Path(__file__).resolve().parents[1] / "tools"
          / "rclone_two_mount_real_probe_lab.py")
spec = importlib.util.spec_from_file_location(
    "_masqelec_oauth_v2_real_lab", SCRIPT)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class ProcScan:
    def __init__(self, processes):
        self._items = [
            types.SimpleNamespace(name=str(4000 + idx),
                                  path="/proc/{}".format(4000 + idx))
            for idx in range(len(processes))
        ]
        self._cmds = {
            entry.path + "/cmdline":
                b"\0".join(s.encode("utf-8") for s in proc) + b"\0"
            for entry, proc in zip(self._items, processes)
        }

    def __iter__(self):
        return iter(self._items)

    def close(self):
        pass

    def open(self, path, mode="rb"):
        return io.BytesIO(self._cmds[path])


class TwoMountRealProbeFenceTests(unittest.TestCase):
    def scan(self, processes):
        listing = ProcScan(processes)
        return (mock.patch.object(lab.os, "scandir", return_value=listing),
                mock.patch("builtins.open", side_effect=listing.open),
                mock.patch.object(lab.os, "getpid", return_value=999999))

    def test_active_mount_blocks_even_if_config_is_private(self):
        ctx = self.scan([
            ["/storage/.config/rclone/rclone", "mount",
             "users_library_1:", "/storage/.mnt/cloud/1",
             "--config", "/storage/.config/rclone/isolated-mounts/account1.conf"],
            ["rclone", "lsf", "one_a:"],
        ])
        with ctx[0], ctx[1], ctx[2]:
            self.assertTrue(lab.any_rclone_mounts_alive())

    def test_rclone_lsf_without_mount_is_not_falsely_active(self):
        ctx = self.scan([
            ["rclone", "lsf", "one_a:"],
            ["/bin/python3", "service.py"],
        ])
        with ctx[0], ctx[1], ctx[2]:
            self.assertFalse(lab.any_rclone_mounts_alive())

    def test_unreadable_proc_blocks_network_oauth_probe(self):
        with mock.patch.object(lab.os, "scandir",
                               side_effect=PermissionError):
            self.assertTrue(lab.any_rclone_mounts_alive())

    def test_github_branch_head_accepted_only_with_full_sha(self):
        good_sha = "a" * 40
        with mock.patch.object(lab, "fetch", return_value=(
                '{"commit":{"sha":"' + good_sha + '"}}').encode()):
            self.assertEqual(lab.github_branch_head(), good_sha)

    def test_github_branch_head_rejects_invalid_response(self):
        for response in (b'{}', b'{"commit":{}}',
                         b'{"commit":{"sha":"abc"}}',
                         b'{"commit":{"sha":"G' + b'a' * 39 + b'"}}'):
            with self.subTest(response=response[:16]), \
                 mock.patch.object(lab, "fetch", return_value=response):
                with self.assertRaises(ValueError):
                    lab.github_branch_head()

    def test_mount_after_many_global_flags_is_still_detected(self):
        args = ["rclone"] + ["--test-flag-{}".format(i) for i in range(12)]
        args += ["mount", "users_library_1:", "/tmp/mount"]
        ctx = self.scan([args])
        with ctx[0], ctx[1], ctx[2]:
            self.assertTrue(lab.any_rclone_mounts_alive())

    def test_oversized_proc_cmdline_fails_closed(self):
        ctx = self.scan([["rclone", "lsf", "x" * 20000]])
        with ctx[0], ctx[1], ctx[2]:
            self.assertTrue(lab.any_rclone_mounts_alive())

    def test_no_local_mounts_still_blocks_uncoordinated_fleet_probe(self):
        output = io.StringIO()
        with mock.patch.object(lab, "any_rclone_mounts_alive",
                               return_value=False), \
             mock.patch.object(lab, "fetch",
                               side_effect=AssertionError("NO_NETWORK")), \
             mock.patch.object(lab, "read_key",
                               side_effect=AssertionError("NO_KEY")), \
             mock.patch.object(sys, "argv",
                               ["rclone_two_mount_real_probe_lab.py",
                                "--real-probe"]), \
             contextlib.redirect_stdout(output):
            self.assertEqual(lab.main(), 2)
        self.assertIn("FLEET_OAUTH_COORDINATION=NOT_VERIFIED",
                      output.getvalue())
        self.assertIn("LAB_RESULT=BLOCKED_FLEET_COORDINATION",
                      output.getvalue())
        self.assertNotIn("GH_BLOB_SHA_VALID=PASS", output.getvalue())

    def test_real_probe_main_exits_before_loading_credentials_if_mounts_alive(self):
        log = io.StringIO()
        with mock.patch.object(lab, "any_rclone_mounts_alive",
                               return_value=True), \
             mock.patch.object(lab, "fetch",
                               side_effect=AssertionError("NO_NETWORK")), \
             mock.patch.object(lab, "read_key",
                               side_effect=AssertionError("NO_KEY")), \
             mock.patch.object(sys, "argv",
                               ["rclone_two_mount_real_probe_lab.py",
                                "--real-probe"]), \
             contextlib.redirect_stdout(log):
            self.assertEqual(lab.main(), 2)
        self.assertIn("LAB_RESULT=BLOCKED_ACTIVE_MOUNTS", log.getvalue())
        self.assertNotIn("GH_BLOB_SHA_VALID=PASS", log.getvalue())


if __name__ == "__main__":
    unittest.main()
