# -*- coding: utf-8 -*-
"""Inventory seguro: fixtures /proc y mountinfo, nunca leer credenciales."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH = (Path(__file__).resolve().parents[1] /
        "tools/rclone_two_mount_fleet_inventory.py")
spec = importlib.util.spec_from_file_location("fleet_inventory", PATH)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


def line(mount, fstype="fuse.rclone"):
    return ("23 1 0:45 / {} rw - {} remote rw".format(
        mount, fstype))


def mock_mounts():
    return "\n".join([line("/dev", "devtmpfs"), line("/proc", "proc")] +
                     [line(path) for path in lab.EXPECTED_LEGACY])


class FleetInventoryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.mountinfo = self.root / "mountinfo"
        self.mountinfo.write_text(mock_mounts())

    def pid(self, pid, comm=b"rclone\n",
            args=(b"/usr/bin/rclone", b"mount", b"remote:", b"/tmp/root")):
        d = self.proc / str(pid)
        d.mkdir()
        (d / "comm").write_bytes(comm)
        (d / "cmdline").write_bytes(b"\0".join(args) + b"\0")
        return d

    def test_four_legacy_fuse_mounts_without_content_read(self):
        data = lab.inspect_mounts(mock_mounts())
        self.assertTrue(data["complete"])
        self.assertEqual(data["legacy"], 4)
        self.assertEqual(data["new"], 0)
        self.assertEqual(data["fuse_total"], 4)
        self.assertEqual(data["extra_fuse"], 0)

    def test_v2_mounts_reported_separately(self):
        allmounts = (mock_mounts() + "\n" +
                     "\n".join(line(p) for p in lab.EXPECTED_V2))
        m = lab.inspect_mounts(allmounts)
        self.assertEqual(m["legacy"], 4)
        self.assertEqual(m["new"], 2)
        self.assertEqual(m["fuse_total"], 6)

    def test_non_rclone_mount_does_not_count_as_legacy(self):
        path = lab.EXPECTED_LEGACY[0]
        text = mock_mounts().replace(
            line(path), line(path, "ext4"))
        m = lab.inspect_mounts(text)
        self.assertTrue(m["complete"])
        self.assertEqual(m["legacy"], 3)
        self.assertEqual(m["fuse_total"], 3)

    def test_non_rclone_mount_does_not_count_as_v2(self):
        text = (mock_mounts() + "\n" +
                line(lab.EXPECTED_V2[0], "tmpfs"))
        m = lab.inspect_mounts(text)
        self.assertTrue(m["complete"])
        self.assertEqual(m["new"], 0)

    def test_mount_stack_not_reported_as_unique_valid(self):
        txt = mock_mounts() + "\n" + line(lab.EXPECTED_LEGACY[0])
        m = lab.inspect_mounts(txt)
        self.assertEqual(m["legacy"], 3)
        self.assertEqual(m["stacked"], 1)

    def test_unrelated_fuse_identified_without_path_leak(self):
        m = lab.inspect_mounts(mock_mounts() + "\n" +
                               line("/another/private/path"))
        self.assertEqual(m["extra_fuse"], 1)

    def test_mountinfo_missing_or_corrupt_denied(self):
        for bad in (None, "", b"\xff", "bad", "1 2 3",
                    "4 5 6 / /tmp abc"):
            with self.subTest(bad=bad):
                self.assertFalse(lab.inspect_mounts(bad)["complete"])

    def test_mountinfo_oversized_denied(self):
        self.assertFalse(lab.inspect_mounts(
            "x" * (lab.MAX_MOUNTINFO + 1))["complete"])

    def test_mountinfo_octal_paths_supported(self):
        m = lab.inspect_mounts(mock_mounts() + "\n" +
                               line("/tmp/with\\040space"))
        self.assertTrue(m["complete"])
        self.assertEqual(m["extra_fuse"], 1)

    def test_zero_processes_is_not_fleet_authorization(self):
        with mock.patch.object(lab, "inventory",
                               return_value=(
                                   {"complete": True, "rclone": 0,
                                    "mount": 0, "other": 0, "uncertain": 0},
                                   {"complete": True, "fuse_total": 0,
                                    "legacy": 0, "new": 0, "stacked": 0,
                                    "extra_fuse": 0})), \
             contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(lab.main(["--inventory"]), 0)
        output = buf.getvalue()
        self.assertIn("FLEET_OAUTH_COORDINATION=NOT_VERIFIED", output)
        self.assertIn("REAL_OAUTH_PROBE_ALLOWED=NO", output)
        self.assertIn("OTHER_DEVICES_INSPECTED=NO", output)
        self.assertNotIn("CUTOVER_AUTHORIZED=YES", output)

    def test_four_live_rclone_mount_processes(self):
        for idx in range(4):
            self.pid(idx + 2)
        p = lab.inspect_processes(str(self.proc))
        self.assertTrue(p["complete"])
        self.assertEqual(p["rclone"], 4)
        self.assertEqual(p["mount"], 4)
        self.assertEqual(p["other"], 0)

    def test_other_rclone_process_may_write_oauth(self):
        self.pid(12, args=(b"/usr/bin/rclone", b"lsf",
                           b"private_remote:", b"--config", b"secret-path"))
        p = lab.inspect_processes(str(self.proc))
        self.assertTrue(p["complete"])
        self.assertEqual(p["other"], 1)
        self.assertEqual(p["mount"], 0)

    def test_empty_rclone_cmdline_fails_closed(self):
        d = self.pid(12)
        (d / "cmdline").write_bytes(b"")
        p = lab.inspect_processes(str(self.proc))
        self.assertFalse(p["complete"])
        self.assertEqual(p["uncertain"], 1)

    def test_non_rclone_process_ignored(self):
        self.pid(6, comm=b"python3\n", args=(b"python3", b"/tmp/a.py"))
        p = lab.inspect_processes(str(self.proc))
        self.assertEqual(p["rclone"], 0)
        self.assertTrue(p["complete"])

    def test_unexpected_rclone_executable_fails_closed(self):
        self.pid(7, args=(b"/usr/bin/other", b"mount", b"test:"))
        p = lab.inspect_processes(str(self.proc))
        self.assertEqual(p["uncertain"], 1)
        self.assertFalse(p["complete"])

    def test_truncated_cmdline_fails_closed(self):
        d = self.pid(8)
        (d / "cmdline").write_bytes(b"x" * (lab.MAX_CMDLINE + 1))
        self.assertFalse(lab.inspect_processes(str(self.proc))["complete"])

    def test_missing_proc_root_fails_closed(self):
        p = lab.inspect_processes(str(self.root / "absent"))
        self.assertFalse(p["complete"])

    def test_binary_metadata_output_does_not_contain_secrets(self):
        self.pid(42, args=(b"/usr/bin/rclone", b"lsf",
                           b"SECRET_REMOTE:", b"--config",
                           b"/secret/tokens/file.conf",
                           b"--password=DO_NOT_PRINT"))
        with mock.patch.object(lab, "inventory",
                               side_effect=lambda: (
                                   lab.inspect_processes(str(self.proc)),
                                   lab.inspect_mounts(mock_mounts()))), \
             contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(lab.main(["--inventory"]), 0)
        output = buf.getvalue()
        for secret in ("SECRET_REMOTE", "DO_NOT_PRINT", "tokens/file",
                       "/secret/", "42", "file.conf"):
            self.assertNotIn(secret, output)
        self.assertIn("RCLONE_OTHER_PROCESSES=1", output)

    def test_invalid_cli_never_reads_proc(self):
        with mock.patch.object(lab, "inventory",
                               side_effect=AssertionError("no read")), \
             contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(lab.main(["--execute"]), 2)
        self.assertEqual(buf.getvalue().strip(),
                         "INVENTORY_RESULT=BLOCKED_INVALID_MODE")

    def test_missing_mountinfo_returns_blocked(self):
        p, m = lab.inventory(str(self.proc),
                             str(self.root / "no-mountinfo"))
        self.assertTrue(p["complete"])
        self.assertFalse(m["complete"])

    def test_source_no_network_mutating_commands_or_config_access(self):
        content = PATH.read_text()
        for forbidden in ("import subprocess", "import urllib",
                          "import socket", "os.system(", "systemctl",
                          "rclone.conf", "rclone lsf", "os.unlink(",
                          "os.rename(", "os.replace(", "os.kill("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, content)

    def test_incomplete_proc_refuses_read_only_pass(self):
        p = {"complete": False, "rclone": 1,
             "mount": 0, "other": 0, "uncertain": 1}
        m = {"complete": True, "fuse_total": 0, "legacy": 0,
             "new": 0, "stacked": 0, "extra_fuse": 0}
        with mock.patch.object(lab, "inventory", return_value=(p, m)), \
             contextlib.redirect_stdout(io.StringIO()) as buf:
            self.assertEqual(lab.main(["--inventory"]), 2)
        self.assertIn("BLOCKED_INCOMPLETE_LOCAL_INSPECTION",
                      buf.getvalue())


if __name__ == "__main__":
    unittest.main()
