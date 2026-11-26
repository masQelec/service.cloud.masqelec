# -*- coding: utf-8 -*-
"""Resolucion cloud desde Kodi y publicacion MQC2 simulada."""

import json
import unittest
from unittest import mock

from lib import constants
from lib import cloud_version_routes as cloud
from lib import rclone_two_mount_master_runtime as runtime
from lib import rclone_two_mount_config_routes as routes
from lib import rclone_two_mount_plan as plan

from test_rclone_mount_isolation import wrapped_conf
from test_rclone_two_mount_master_sync import StableGH


def reply(major):
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "version": {
                "major": major,
                "minor": 2,
            }
        }
    })


class CloudRuntimeRoutesTests(unittest.TestCase):

    def test_real_rpc_request_format(self):
        def rpc(raw):
            request = json.loads(raw)

            self.assertEqual(
                request["method"],
                "Application.GetProperties"
            )

            self.assertEqual(
                request["params"],
                {"properties": ["version"]}
            )

            return reply(21)

        branch, base = cloud.route_from_kodi_rpc(rpc)

        self.assertEqual(branch, "21")

        self.assertEqual(
            base,
            "https://raw.githubusercontent.com/"
            "masQelec/cloud.masqelec/21"
        )

    def test_future_version_routes(self):
        for major in (22, 23, 24):
            branch, base = cloud.route_from_kodi_rpc(
                lambda raw: reply(major)
            )

            self.assertEqual(branch, str(major))
            self.assertTrue(base.endswith("/" + branch))

    def test_invalid_rpc_response_has_no_fallback(self):
        for raw in (
            None, "", "not-json", "null", "[]",
            "{}",
            '{"jsonrpc":"2.0","id":1,"error":{}}',
            '{"jsonrpc":"2.0","id":2,"result":{}}',
            '{"jsonrpc":"2.0","id":true,"result":{}}',
        ):
            with self.subTest(raw=raw):
                with self.assertRaises(
                    cloud.CloudVersionError
                ):
                    cloud.route_from_kodi_rpc(
                        lambda request: raw
                    )

    def test_invalid_major_has_no_fallback(self):
        for major in (None, True, "21", 0, -1):
            with self.subTest(major=major):
                with self.assertRaises(
                    cloud.CloudVersionError
                ):
                    cloud.route_from_kodi_rpc(
                        lambda raw: reply(major)
                    )

    def test_rpc_exception_has_no_fallback(self):
        def failed(request):
            raise RuntimeError("RPC unavailable")

        with self.assertRaisesRegex(
            cloud.CloudVersionError,
            "^KODI_VERSION_UNAVAILABLE$"
        ):
            cloud.route_from_kodi_rpc(failed)

    def test_master_pipeline_branch_21(self):
        """Motor MQC2 completo con transporte sintetico."""

        key = b"K" * 32
        canonical = wrapped_conf("crypt")

        accounts = tuple(
            plan.account_snapshot(canonical, i)
            for i in (0, 1)
        )

        github = StableGH(key)
        calls = []

        def request(method, url, token, payload=None):
            calls.append((method, url))

            if url.endswith("/branches/21"):
                return 200, {
                    "commit": {"sha": github.head()}
                }

            if method == "GET":
                self.assertTrue(url.endswith(
                    "/rclone/rclone-v2.conf.crypt?ref=21"
                ))

                return github.get(routes.V2_REMOTE_PATH)

            if method == "PUT":
                self.assertTrue(url.endswith(
                    "/rclone/rclone-v2.conf.crypt"
                ))

                self.assertEqual(payload["branch"], "21")

                return github.put(
                    routes.V2_REMOTE_PATH,
                    payload
                )

            self.fail("Unexpected request")

        with mock.patch.object(
            constants, "CLOUD_BRANCH", "21"
        ), mock.patch.object(
            constants,
            "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
            True
        ), mock.patch.object(
            constants,
            "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
            True
        ), mock.patch.object(
            runtime, "_get_role", return_value="MASTER"
        ), mock.patch.object(
            runtime.rollout, "mode", return_value="active"
        ):
            result = runtime.run_once(
                release_authorized=True,
                key=key,
                token="TEST",
                request=request,
                sources=lambda: (canonical, accounts),
                probe=lambda candidate, names: {
                    name: "ok" for name in names
                },
            )

        self.assertEqual(result, "created_verified")

        self.assertEqual(
            sum(method == "PUT" for method, url in calls),
            1
        )

        for method, url in calls:
            self.assertNotIn("/develop", url)
            self.assertNotIn("ref=develop", url)


if __name__ == "__main__":
    unittest.main()
