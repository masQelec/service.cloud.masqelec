# -*- coding: utf-8 -*-
"""Transporte GH/MASTER con stubs; sin credenciales ni peticiones reales."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_master_runtime as runtime
from lib import rclone_two_mount_config_routes as routes
from lib import constants


class MasterV2RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []

    def request(self, method, url, token, payload=None):
        self.calls.append((method, url, payload))
        if "/branches/" in url:
            return 200, {"commit": {"sha": "a" * 40}}
        if method == "GET":
            return 404, {"message": "Not Found"}
        if method == "PUT":
            return 409, {"message": "Conflict"}
        raise AssertionError("bad method")

    def test_head_get_put_use_only_v2_cloud_path(self):
        t = runtime.GitHubV2Transport("TEST_GH_TOKEN", self.request)
        self.assertEqual(t.head(), "a" * 40)
        status, _ = t.get(routes.V2_REMOTE_PATH)
        self.assertEqual(status, 404)
        status, _ = t.put(routes.V2_REMOTE_PATH, {
            "branch": "develop", "content": "fake", "message": "test"})
        self.assertEqual(status, 409)
        self.assertEqual(self.calls[0][1],
                         "https://api.github.com/repos/masQelec/cloud.masqelec/branches/develop")
        for op, url, _ in self.calls[1:]:
            self.assertTrue(url.startswith(
                "https://api.github.com/repos/masQelec/cloud.masqelec/contents/rclone/rclone-v2.conf.crypt"))
            self.assertNotIn("rclone.conf.crypt?", url)

    def test_legacy_destination_always_denied(self):
        t = runtime.GitHubV2Transport("TEST", self.request)
        for method in (lambda: t.get(routes.LEGACY_REMOTE_PATH),
                       lambda: t.put(routes.LEGACY_REMOTE_PATH,
                                     {"branch": "develop"})):
            with self.assertRaises(ValueError):
                method()
        self.assertFalse(self.calls)

    def test_other_branch_denied(self):
        t = runtime.GitHubV2Transport("TEST", self.request)
        with self.assertRaises(ValueError):
            t.put(routes.V2_REMOTE_PATH, {"branch": "master"})
        self.assertEqual(self.calls, [])

    def test_no_token_fails_before_http(self):
        with self.assertRaises(ValueError):
            runtime.GitHubV2Transport("", self.request)
        self.assertEqual(self.calls, [])

    def test_head_invalid_json_is_not_authorization(self):
        def response(method, url, token, payload=None):
            return 200, "not-json"
        t = runtime.GitHubV2Transport("TEST", response)
        self.assertIsNone(t.head())

    def test_head_403_is_not_authorization(self):
        def response(method, url, token, payload=None):
            return 403, {"message": "Forbidden"}
        t = runtime.GitHubV2Transport("TEST", response)
        self.assertIsNone(t.head())

    def test_status_none_blocks(self):
        t = runtime.GitHubV2Transport("TEST", lambda *a: (None, "error"))
        self.assertEqual(t.get(routes.V2_REMOTE_PATH), (None, None))

    def test_response_too_large_blocks(self):
        t = runtime.GitHubV2Transport(
            "TEST", lambda *a: (200, "A" * (runtime.MAX_HTTP_BODY + 1)))
        self.assertEqual(t.get(routes.V2_REMOTE_PATH), (None, None))

    def test_run_default_blocked_without_network(self):
        with mock.patch.object(runtime, "GitHubV2Transport",
                               side_effect=AssertionError("network")):
            self.assertEqual(runtime.run_once(), "blocked_not_authorized")

    def test_master_flag_off_blocks_without_probing(self):
        with mock.patch.object(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                               True), \
             mock.patch.object(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
                               False, create=True), \
             mock.patch.object(runtime, "GitHubV2Transport",
                               side_effect=AssertionError("network")):
            self.assertEqual(
                runtime.run_once(release_authorized=True),
                "blocked_master_not_ready")

    def test_not_master_blocks_without_probing(self):
        with mock.patch.object(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                               True), \
             mock.patch.object(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
                               True, create=True), \
             mock.patch.object(runtime, "_get_role",
                               return_value="CLIENT"), \
             mock.patch.object(runtime, "GitHubV2Transport",
                               side_effect=AssertionError("network")):
            self.assertEqual(runtime.run_once(release_authorized=True),
                             "blocked_master_not_ready")

    def test_legacy_mode_blocks_even_with_enabled_flags(self):
        with mock.patch.object(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                               True), \
             mock.patch.object(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
                               True, create=True), \
             mock.patch.object(runtime, "_get_role",
                               return_value="MASTER"), \
             mock.patch.object(runtime.rollout, "mode",
                               return_value="legacy"), \
             mock.patch.object(runtime, "GitHubV2Transport",
                               side_effect=AssertionError("network")):
            self.assertEqual(runtime.run_once(release_authorized=True),
                             "blocked_master_not_ready")

    def test_active_master_invokes_pipeline_with_real_callbacks(self):
        fake = object()
        with mock.patch.object(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                               True), \
             mock.patch.object(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
                               True, create=True), \
             mock.patch.object(runtime, "_get_role",
                               return_value="MASTER"), \
             mock.patch.object(runtime.rollout, "mode",
                               return_value="active"), \
             mock.patch.object(runtime.master, "sync_once",
                               return_value="created_verified") as sync:
            self.assertEqual(runtime.run_once(
                release_authorized=True, key=b"K"*32,
                token="TEST", request=self.request,
                sources=lambda: fake, probe=lambda a, b: {}),
                "created_verified")
            self.assertTrue(sync.called)
            self.assertEqual(self.calls, [])

    def test_probe_callback_is_not_called_with_release_false(self):
        with mock.patch.object(runtime, "_probe_candidate",
                               side_effect=AssertionError("oauth")):
            self.assertEqual(runtime.run_once(), "blocked_not_authorized")

    def test_http_not_called_with_wrong_branch(self):
        with mock.patch.object(constants, "CLOUD_BRANCH", "master"):
            self.assertEqual(runtime.run_once(release_authorized=True),
                             "blocked_master_not_ready")
        self.assertEqual(self.calls, [])

    def test_source_has_no_direct_activation_command(self):
        txt = (Path(__file__).resolve().parents[1] /
               "lib/rclone_two_mount_master_runtime.py").read_text()
        for bad in ("systemctl", "os.system(", "subprocess.run",
                    "rclone mount", "umount "):
            with self.subTest(bad=bad):
                self.assertNotIn(bad, txt)


if __name__ == "__main__":
    unittest.main()
