# -*- coding: utf-8 -*-
"""Piloto rclone 2 FUSE+4 bind: tests sintéticos sin montajes reales."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / (
    "tools/rclone_two_mount_fuse_bind_local_lab.py")
spec = importlib.util.spec_from_file_location("local_fuse_lab", SCRIPT)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class LocalFuseBindPilotTests(unittest.TestCase):
    def test_alternate_paths_never_use_storage(self):
        root = Path("/tmp/masqelec-fuse-local-ABCDE")
        fuse, binds, sources = lab.layout(root)
        self.assertEqual(len(fuse), 2)
        self.assertEqual(len(binds), 4)
        for path in fuse + tuple(x[2] for x in binds):
            self.assertTrue(path.startswith(str(root) + "/"))
            self.assertNotIn("/storage/", path)
        for index, folder, _ in binds:
            self.assertIn(index, (0, 1))
            self.assertIn(folder, ("movies", "tvshows"))
        self.assertEqual(len(sources), 2)

    def test_arbitrary_root_forbidden(self):
        for path in ("/storage/.mnt", "/tmp", "/tmp/other-prefix",
                     "/mnt/masqelec-fuse-local-bad"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                lab.layout(path)

    def test_safe_environment_filters_rclone_config(self):
        env = {
            "PATH": "/usr/bin", "RCLONE_CONFIG": "/storage/secret",
            "RCLONE_ONEDRIVE_TOKEN": "secret", "AWS_ACCESS_KEY_ID": "key",
            "GOOGLE_APPLICATION_CREDENTIALS": "keyfile",
            "ONEDRIVE_TOKEN": "secret",
        }
        with mock.patch.dict(os.environ, env, clear=True):
            filtered = lab._safe_environment()
        self.assertEqual(filtered, {"PATH": "/usr/bin"})

    def test_preflight_never_attempts_pilot(self):
        ready = {k: True for k in (
            "rclone", "mount", "umount", "fuse_device", "mountinfo",
            "privileged")}
        with mock.patch.object(lab, "prerequisites", return_value=ready), \
             mock.patch.object(lab, "run_local_pilot",
                               side_effect=AssertionError("must not mount")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--preflight"]), 0)
        self.assertIn("TYPE_NOTIFY_REAL_SYSTEMD=NOT_TESTED", out.getvalue())

    def test_preflight_missing_fuse_blocks(self):
        prereqs = {k: True for k in (
            "rclone", "mount", "umount", "fuse_device", "mountinfo",
            "privileged")}
        prereqs["fuse_device"] = False
        with mock.patch.object(lab, "prerequisites", return_value=prereqs), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--preflight"]), 2)
        self.assertIn("LAB_RESULT=BLOCKED_MISSING_LOCAL_PREREQUISITE",
                      out.getvalue())

    def test_run_without_confirmation_blocks(self):
        with mock.patch.object(lab, "run_local_pilot",
                               side_effect=AssertionError("must not mount")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--run-local-pilot"]), 2)
        self.assertIn("LAB_RESULT=BLOCKED_INVALID_MODE", out.getvalue())

    def test_invalid_args_block(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--run-local-pilot", "--preflight"]), 2)
        self.assertIn("LAB_RESULT=BLOCKED_INVALID_MODE", out.getvalue())

    def test_local_pilot_result_is_not_production_authorization(self):
        with mock.patch.object(lab, "run_local_pilot",
                               return_value="PASS_LOCAL_FUSE_BIND_LAB"), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(
                ["--run-local-pilot", "--confirm-isolated-only"]), 0)
        self.assertIn("ONEDRIVE_ACCESSED=NO", out.getvalue())
        self.assertIn("KODI_PATHS_CHANGED=NO", out.getvalue())

    def test_local_pilot_failure_propagates_no_false_pass(self):
        with mock.patch.object(lab, "run_local_pilot",
                               return_value="FAIL_LOCAL_MOUNTINFO_LAYOUT"), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(
                ["--run-local-pilot", "--confirm-isolated-only"]), 2)
        self.assertIn("FAIL_LOCAL_MOUNTINFO_LAYOUT", out.getvalue())

    def test_cleanup_no_mounts_removes_only_lab_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "masqelec-fuse-local-test"
            root.mkdir()
            fuse, binds, _ = lab.layout(
                Path("/tmp/masqelec-fuse-local-test"))
            with mock.patch.object(lab, "_is_mounted", return_value=False):
                self.assertTrue(lab._cleanup(root, binds, fuse, []))
            self.assertFalse(root.exists())

    def test_cleanup_mounted_still_never_deletes_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "masqelec-fuse-local-test"
            root.mkdir()
            fuse, binds, _ = lab.layout(
                Path("/tmp/masqelec-fuse-local-test"))
            with mock.patch.object(lab, "_is_mounted", return_value=True), \
                 mock.patch.object(lab, "_run",
                                   side_effect=OSError("denied")):
                self.assertFalse(lab._cleanup(root, binds, fuse, []))
            self.assertTrue(root.exists())

    def test_run_local_blocks_if_missing_root(self):
        prereqs = {k: True for k in (
            "rclone", "mount", "umount", "fuse_device", "mountinfo",
            "privileged")}
        prereqs["privileged"] = False
        with mock.patch.object(lab, "prerequisites", return_value=prereqs):
            self.assertEqual(lab.run_local_pilot(),
                             "BLOCKED_MISSING_LOCAL_PREREQUISITE")

    def test_no_credential_file_or_kodi_paths_in_source(self):
        text = SCRIPT.read_text()
        self.assertNotIn('"/storage/.config/rclone/rclone.conf"', text)
        self.assertNotIn("rclone lsf", text)
        self.assertNotIn('"systemctl"', text)



    def test_kodielec_binary_preferred_to_path(self):
        def is_file(path):
            return path == "/storage/.config/rclone/rclone"
        with mock.patch.object(lab.os.path, "isfile",
                               side_effect=is_file), \
             mock.patch.object(lab.os, "access", return_value=True), \
             mock.patch.object(lab.shutil, "which",
                               side_effect=AssertionError("PATH not needed")):
            self.assertEqual(lab.rclone_binary(),
                             "/storage/.config/rclone/rclone")

    def test_help_checks_flags_without_oauth(self):
        fake = types.SimpleNamespace(
            returncode=0,
            stdout=b"--config --read-only --vfs-cache-mode")
        with mock.patch.object(lab.subprocess, "run",
                               return_value=fake) as run:
            self.assertTrue(lab._rclone_mount_flags_supported("/tmp/rclone"))
            self.assertEqual(run.call_args.args[0],
                             ["/tmp/rclone", "mount", "--help"])

    def test_help_missing_flag_blocks_pilot(self):
        fake = types.SimpleNamespace(
            returncode=0, stdout=b"--config --read-only")
        with mock.patch.object(lab.subprocess, "run", return_value=fake):
            self.assertFalse(lab._rclone_mount_flags_supported("/tmp/rclone"))

    def test_help_timeout_blocks(self):
        with mock.patch.object(lab.subprocess, "run",
                               side_effect=lab.subprocess.TimeoutExpired(
                                   cmd="rclone", timeout=12)):
            self.assertFalse(lab._rclone_mount_flags_supported("/tmp/rclone"))



    def _exercise_full_pilot_mock(self, cleanup_result):
        class DummyProcess:
            pass
        info = {key: True for key in (
            "rclone", "rclone_mount_flags", "mount", "umount",
            "fuse_device", "mountinfo", "privileged")}
        with tempfile.TemporaryDirectory(
                prefix="masqelec-fuse-local-", dir="/tmp") as root:
            with mock.patch.object(lab, "prerequisites", return_value=info), \
                 mock.patch.object(lab.tempfile, "mkdtemp",
                                   return_value=root), \
                 mock.patch.object(lab, "rclone_binary",
                                   return_value="/usr/bin/rclone"), \
                 mock.patch.object(lab, "_wait_for_fuse",
                                   return_value=True), \
                 mock.patch.object(lab, "_run"), \
                 mock.patch.object(lab, "_mountinfo",
                                   return_value="synthetic-mountinfo"), \
                 mock.patch.object(lab, "_check_alternate_layout",
                                   return_value=True), \
                 mock.patch.object(lab, "_cleanup",
                                   return_value=cleanup_result), \
                 mock.patch.object(lab.subprocess, "Popen",
                                   return_value=DummyProcess()), \
                 mock.patch("builtins.open",
                            return_value=io.BytesIO(lab._SAMPLE)), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                result = lab.run_local_pilot()
        return result, output.getvalue()

    def test_clean_lab_success_requires_cleanup(self):
        result, output = self._exercise_full_pilot_mock(True)
        self.assertEqual(result, "PASS_LOCAL_FUSE_BIND_LAB")
        self.assertNotIn("CLEANUP=INCOMPLETE", output)

    def test_cleanup_failure_overrides_success(self):
        result, output = self._exercise_full_pilot_mock(False)
        self.assertEqual(result, "FAIL_LOCAL_CLEANUP")
        self.assertIn("CLEANUP=INCOMPLETE", output)


if __name__ == "__main__":
    unittest.main()
