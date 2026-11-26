# -*- coding: utf-8 -*-
"""Politica definitiva de distribucion cloud."""

import unittest
from unittest import mock

from lib import constants
from lib import cloud_version_routes as cloud
from lib import rclone_two_mount_master_sync as master
from lib import rclone_two_mount_publish_guard as publisher
from lib import rclone_two_mount_master_runtime as runtime
from lib import rclone_two_mount_v2_publication as publication


class CloudReleasePolicyTests(unittest.TestCase):

    def forbidden(self, *args, **kwargs):
        self.fail("Unexpected callback")

    def test_only_validated_numeric_release_allowed(self):
        self.assertTrue(
            cloud.rclone_transport_branch_allowed("21")
        )

        for branch in (
            None, "", "develop", "master",
            "main", "22", "23", "021", "../21"
        ):
            with self.subTest(branch=branch):
                self.assertFalse(
                    cloud.rclone_transport_branch_allowed(
                        branch
                    )
                )

    def test_master_requires_explicit_branch(self):
        with self.assertRaises(TypeError):
            master.sync_once(
                self.forbidden, self.forbidden,
                self.forbidden, self.forbidden,
                self.forbidden, b"K" * 32, "TEST",
                release_authorized=True,
                master_attested=True,
            )

    def test_publisher_requires_explicit_branch(self):
        with self.assertRaises(TypeError):
            publisher.strict_put(
                "TEST", b"synthetic",
                "a" * 40, self.forbidden,
                release_authorized=True,
                sources_revalidated=True,
                remote_authenticated=True,
            )

    def test_develop_master_publication_blocked(self):
        result = master.sync_once(
            self.forbidden, self.forbidden,
            self.forbidden, self.forbidden,
            self.forbidden, b"K" * 32, "TEST",
            release_authorized=True,
            master_attested=True,
            branch="develop",
        )

        self.assertEqual(
            result, "blocked_not_authorized"
        )

    def test_develop_cas_publication_blocked(self):
        result = publisher.strict_put(
            "TEST", b"synthetic",
            "a" * 40, self.forbidden,
            release_authorized=True,
            sources_revalidated=True,
            remote_authenticated=True,
            branch="develop",
        )

        self.assertEqual(result, "blocked")

    def test_unresolved_or_develop_transport_blocked(self):
        for branch in (None, "develop"):
            with mock.patch.object(
                constants, "CLOUD_BRANCH", branch
            ):
                with self.assertRaises(ValueError):
                    runtime.GitHubV2Transport(
                        "TEST", self.forbidden
                    )

    def test_develop_raw_availability_blocked(self):
        with mock.patch.object(
            constants, "CLOUD_BRANCH", "develop"
        ), mock.patch.object(
            constants, "CLOUD_RAW_BASE",
            "https://raw.githubusercontent.com/"
            "masQelec/cloud.masqelec/develop"
        ):
            self.assertFalse(
                publication.available(self.forbidden)
            )


if __name__ == "__main__":
    unittest.main()
