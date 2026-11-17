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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

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

    def _simulate_divergent_preflight(self, *, remote_head_drift=False):
        """Ejercita main completo con MQC2 ficticio y sin red ni montajes."""
        import base64
        import json
        from lib import rclone_token_policy as policy
        from lib import rclone_two_mount_plan as plan
        from lib import rclone_two_mount_oauth as coordinator
        from lib import rclone_two_mount_publish_guard as publisher
        from lib import rclone_two_mount_verify as verifier
        from test_rclone_mount_isolation import wrapped_conf

        canonical = wrapped_conf("crypt")
        remote = canonical.replace(
            b"refresh-users_library_2", b"fictional-remote-refresh")
        key = b"K" * 32
        encrypted = publisher.encode_candidate(remote, key)
        gh_body = json.dumps({
            "sha": publisher.git_blob_sha(encrypted),
            "encoding": "base64",
            "content": base64.b64encode(encrypted).decode("ascii"),
        }).encode("utf-8")
        first_sha, next_sha = "a" * 40, "b" * 40
        branch_reads = [0]

        def fake_fetch(url):
            if url.startswith(lab.SOURCE):
                return b"# local mock, never executed\n"
            if url == lab.BRANCH_URL:
                branch_reads[0] += 1
                sha = (next_sha if remote_head_drift and
                       branch_reads[0] > 1 else first_sha)
                return json.dumps({"commit": {"sha": sha}}).encode()
            if url == lab.CONTENTS_URL.replace(
                    "?ref=develop", "?ref=" + first_sha):
                return gh_body
            raise AssertionError("Unexpected network URL")

        modules = {
            "lib.rclone_token_policy": policy,
            "lib.rclone_two_mount_plan": plan,
            "lib.rclone_two_mount_oauth": coordinator,
            "lib.rclone_two_mount_publish_guard": publisher,
            "lib.rclone_two_mount_verify": verifier,
        }
        output = io.StringIO()
        with mock.patch.object(lab, "fetch", side_effect=fake_fetch), \
             mock.patch.object(lab, "read_key", return_value=key), \
             mock.patch.object(lab, "read_live_stable",
                               return_value=canonical) as local_reads, \
             mock.patch.object(lab, "which_rclone",
                               side_effect=AssertionError("NO_RCLONE")), \
             mock.patch.object(lab.importlib, "import_module",
                               side_effect=lambda name: modules[name]), \
             mock.patch.object(sys, "argv", ["probe.py", "--preflight"]), \
             contextlib.redirect_stdout(output):
            result = lab.main()
        self.assertEqual(local_reads.call_count, 2)
        self.assertEqual(branch_reads[0], 2)
        return result, output.getvalue()

    def test_main_divergent_preflight_blocks_without_secrets(self):
        code, output = self._simulate_divergent_preflight()
        self.assertEqual(code, 2)
        self.assertIn("BASELINE_REFRESH_ONEDRIVE_2=DIFFERENT", output)
        self.assertIn("BASELINE_REFRESH_ONEDRIVE_1=SAME", output)
        self.assertIn("GH_BRANCH_COMMIT_STABLE=YES", output)
        self.assertIn("REAL_OAUTH_PROBE=NOT_EXECUTED", output)
        self.assertIn("GITHUB_PUBLISH_ALLOWED=NO", output)
        self.assertIn("LAB_RESULT=BLOCKED_BASELINE_DIVERGED", output)
        self.assertNotIn("fictional-remote-refresh", output)
        self.assertNotIn("refresh-users_library", output)
        self.assertNotIn("one_b", output)

    def test_main_divergent_preflight_refuses_changed_github_branch(self):
        code, output = self._simulate_divergent_preflight(
            remote_head_drift=True)
        self.assertEqual(code, 2)
        self.assertIn("GH_BRANCH_COMMIT_STABLE=NO", output)
        self.assertIn("LAB_RESULT=INCONCLUSIVE_GITHUB_UPDATED", output)
        self.assertNotIn("BASELINE_REFRESH_ONEDRIVE_2", output)
        self.assertNotIn("LAB_RESULT=BLOCKED_BASELINE_DIVERGED", output)

    def test_refresh_report_same_four_accounts_never_prints_tokens(self):
        from lib import rclone_token_policy as policy
        from lib import rclone_two_mount_plan as plan
        from test_rclone_mount_isolation import wrapped_conf
        conf = wrapped_conf("crypt")
        report = lab.baseline_refresh_report(conf, conf, policy, plan)
        self.assertEqual(report, (
            ("ONEDRIVE_1", "SAME"), ("ONEDRIVE_2", "SAME"),
            ("DRIVE_1", "SAME"), ("DRIVE_2", "SAME")))
        self.assertNotIn("refresh-", str(report))
        self.assertNotIn("one_a", str(report))

    def test_refresh_report_distinguishes_onedrive_and_drive(self):
        from lib import rclone_token_policy as policy
        from lib import rclone_two_mount_plan as plan
        from test_rclone_mount_isolation import wrapped_conf
        local = wrapped_conf("crypt")
        remote = local.replace(b"refresh-users_library_2", b"other-one")
        remote = remote.replace(b"refresh-updater", b"other-google")
        report = dict(lab.baseline_refresh_report(local, remote, policy, plan))
        self.assertEqual(report["ONEDRIVE_1"], "SAME")
        self.assertEqual(report["ONEDRIVE_2"], "DIFFERENT")
        self.assertEqual(sum(v == "DIFFERENT" for v in report.values()), 2)
        self.assertEqual(sum(v == "DIFFERENT" for k, v in report.items()
                             if k.startswith("DRIVE_")), 1)

    def test_refresh_report_ignores_access_token_only_change(self):
        from lib import rclone_token_policy as policy
        from lib import rclone_two_mount_plan as plan
        from test_rclone_mount_isolation import wrapped_conf
        local = wrapped_conf("crypt")
        remote = local.replace(b"access-users_library_1", b"other-access")
        report = lab.baseline_refresh_report(local, remote, policy, plan)
        self.assertTrue(all(state == "SAME" for _, state in report))

    def test_refresh_report_rejects_invalid_layout(self):
        from lib import rclone_token_policy as policy
        from lib import rclone_two_mount_plan as plan
        from test_rclone_mount_isolation import wrapped_conf
        local = wrapped_conf("crypt")
        broken = local.replace(b"type = onedrive", b"type = alias", 1)
        with self.assertRaises(ValueError):
            lab.baseline_refresh_report(local, broken, policy, plan)

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
