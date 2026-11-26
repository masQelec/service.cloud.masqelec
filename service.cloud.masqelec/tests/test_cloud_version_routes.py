# -*- coding: utf-8 -*-
"""Pruebas aisladas de selección cloud por versión Kodi."""

import sys
import unittest
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1])
)

from lib import cloud_version_routes as routes


class CloudVersionRoutesTests(unittest.TestCase):

    def test_kodi_21_minor_versions(self):
        for minor in (0, 1, 2, 3, 9):
            with self.subTest(minor=minor):
                self.assertEqual(
                    routes.branch_from_version({
                        "major": 21,
                        "minor": minor,
                    }),
                    "21",
                )

    def test_future_versions(self):
        for major in (22, 23, 24):
            self.assertEqual(
                routes.branch_from_version({
                    "major": major
                }),
                str(major),
            )

    def test_invalid_version(self):
        for version in (
            None, "", [], True, 21, {},
            {"major": None},
            {"major": True},
            {"major": "21"},
            {"major": 21.2},
            {"major": 0},
            {"major": -1},
            {"major": 100},
        ):
            with self.subTest(version=version):
                with self.assertRaises(
                    routes.CloudVersionError
                ):
                    routes.branch_from_version(version)

    def test_provider(self):
        self.assertEqual(
            routes.resolve_branch(
                lambda: {"major": 21, "minor": 2}
            ),
            "21",
        )

    def test_provider_failure(self):
        def failed():
            raise RuntimeError("private diagnostic")

        with self.assertRaisesRegex(
            routes.CloudVersionError,
            "^KODI_VERSION_UNAVAILABLE$"
        ):
            routes.resolve_branch(failed)

    def test_invalid_provider(self):
        with self.assertRaises(routes.CloudVersionError):
            routes.resolve_branch(None)

    def test_raw_url(self):
        self.assertEqual(
            routes.raw_base_for_branch("21"),
            "https://raw.githubusercontent.com/"
            "masQelec/cloud.masqelec/21",
        )

    def test_invalid_branches(self):
        for branch in (
            None, True, 21, "", "0", "021",
            "100", "develop", "main", "master",
            "kodi-21", "../21", "21/test",
            "21?ref=main", "21#x", "21\n",
            "２１", "21.2",
        ):
            with self.subTest(branch=branch):
                self.assertFalse(
                    routes.valid_version_branch(branch)
                )
                self.assertFalse(
                    routes.rclone_release_branch_allowed(
                        branch
                    )
                )
                with self.assertRaises(
                    routes.CloudVersionError
                ):
                    routes.raw_base_for_branch(branch)

    def test_release_branch_separate_from_routing(self):
        self.assertTrue(
            routes.rclone_release_branch_allowed("21")
        )

        for branch in ("20", "22", "23"):
            self.assertTrue(
                routes.valid_version_branch(branch)
            )
            self.assertFalse(
                routes.rclone_release_branch_allowed(
                    branch
                )
            )


if __name__ == "__main__":
    unittest.main()
