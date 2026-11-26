# -*- coding: utf-8 -*-
"""Enrutamiento cloud MQC2 sin red ni credenciales reales."""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)

from lib import constants
from lib import cloud_version_routes as cloud
from lib import rclone_two_mount_master_runtime as runtime
from lib import rclone_two_mount_master_sync as master
from lib import rclone_two_mount_config_routes as routes
from lib import rclone_two_mount_publish_guard as publisher
from lib import rclone_two_mount_v2_publication as publication


class CloudRcloneBranchTests(unittest.TestCase):

    def setUp(self):
        self.calls = []

    def request(self, method, url, token, payload=None):
        self.calls.append((method, url, payload))

        if "/branches/" in url:
            return 200, {
                "commit": {"sha": "a" * 40}
            }

        return 404, {}

    def test_branch_policy(self):
        for branch in ("21",):
            self.assertTrue(
                cloud.rclone_transport_branch_allowed(branch)
            )

        for branch in (
            "main", "master", "develop", "22",
            "23", "../21", "", None
        ):
            self.assertFalse(
                cloud.rclone_transport_branch_allowed(branch)
            )

    def test_branch_21_head_get_put(self):
        with mock.patch.object(
            constants, "CLOUD_BRANCH", "21"
        ):
            transport = runtime.GitHubV2Transport(
                "TEST", self.request
            )

            self.assertEqual(transport.branch, "21")
            self.assertEqual(transport.head(), "a" * 40)

            transport.get(routes.V2_REMOTE_PATH)

            transport.put(
                routes.V2_REMOTE_PATH,
                {"branch": "21"}
            )

        self.assertTrue(
            self.calls[0][1].endswith("/branches/21")
        )

        self.assertTrue(
            self.calls[1][1].endswith(
                "/rclone/rclone-v2.conf.crypt?ref=21"
            )
        )

        self.assertEqual(
            self.calls[2][2]["branch"], "21"
        )

    def test_mismatched_put_branch_blocked(self):
        with mock.patch.object(
            constants, "CLOUD_BRANCH", "21"
        ):
            transport = runtime.GitHubV2Transport(
                "TEST", self.request
            )

            for branch in ("develop", "main", "22"):
                with self.assertRaises(ValueError):
                    transport.put(
                        routes.V2_REMOTE_PATH,
                        {"branch": branch}
                    )

        self.assertEqual(self.calls, [])

    def test_transport_pins_branch(self):
        with mock.patch.object(
            constants, "CLOUD_BRANCH", "21"
        ):
            transport = runtime.GitHubV2Transport(
                "TEST", self.request
            )

        with mock.patch.object(
            constants, "CLOUD_BRANCH", "develop"
        ):
            transport.head()
            transport.get(routes.V2_REMOTE_PATH)

        self.assertTrue(
            self.calls[0][1].endswith("/branches/21")
        )

        self.assertTrue(
            self.calls[1][1].endswith("?ref=21")
        )

    def test_unsupported_branch_blocks_transport(self):
        for branch in ("main", "master", "develop", "22"):
            with mock.patch.object(
                constants, "CLOUD_BRANCH", branch
            ):
                with self.assertRaises(ValueError):
                    runtime.GitHubV2Transport(
                        "TEST", self.request
                    )

        self.assertEqual(self.calls, [])

    def test_raw_branch_consistency(self):
        base = cloud.raw_base_for_branch("21")

        self.assertTrue(
            cloud.rclone_transport_base_matches("21", base)
        )

        self.assertFalse(
            cloud.rclone_transport_base_matches(
                "develop", base
            )
        )

        self.assertFalse(
            cloud.rclone_transport_base_matches(
                "21", base + "/extra"
            )
        )

    def test_publication_wrong_raw_branch_blocks_network(self):
        with mock.patch.object(
            constants, "CLOUD_BRANCH", "21"
        ), mock.patch.object(
            constants,
            "CLOUD_RAW_BASE",
            "https://raw.githubusercontent.com/"
            "masQelec/cloud.masqelec/develop"
        ):
            self.assertFalse(
                publication.available(
                    lambda *a, **k: self.fail(
                        "Unexpected network"
                    )
                )
            )

    def test_master_invalid_branch_blocks_callbacks(self):
        def forbidden(*args, **kwargs):
            self.fail("Unexpected callback")

        result = master.sync_once(
            forbidden, forbidden, forbidden,
            forbidden, forbidden,
            b"K" * 32, "TEST",
            release_authorized=True,
            master_attested=True,
            branch="main",
        )

        self.assertEqual(
            result, "blocked_not_authorized"
        )

    def test_cas_publisher_branch_21(self):
        calls = []

        def request(token, path, payload):
            calls.append(payload)
            return 409, {}

        result = publisher.strict_put(
            "TEST",
            b"synthetic",
            "a" * 40,
            request,
            release_authorized=True,
            sources_revalidated=True,
            remote_authenticated=True,
            branch="21",
        )

        self.assertEqual(
            result, "remote_conflict_no_retry"
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["branch"], "21")


if __name__ == "__main__":
    unittest.main()
