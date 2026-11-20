# -*- coding: utf-8 -*-
"""Contratos MQC2 por versión; no red, disco secreto ni systemd."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_config_routes as routes


class MQC2ConfigRouteTests(unittest.TestCase):
    def test_legacy_keeps_original_filename(self):
        self.assertEqual(
            routes.remote_path_for_mount_mode("legacy"),
            "rclone/rclone.conf.crypt")

    def test_prepared_keeps_original_filename_until_cutover(self):
        self.assertEqual(
            routes.remote_path_for_mount_mode("prepared"),
            routes.LEGACY_REMOTE_PATH)

    def test_active_selects_distinct_versioned_filename(self):
        self.assertEqual(
            routes.remote_path_for_mount_mode("active"),
            "rclone/rclone-v2.conf.crypt")
        self.assertNotEqual(routes.V2_REMOTE_PATH, routes.LEGACY_REMOTE_PATH)

    def test_unsafe_or_transitory_modes_never_fallback_to_legacy(self):
        for state in ("unsafe", "cutover_started", "rollback_required",
                      "cleanup_pending", "corrupt", ""):
            with self.subTest(state=state), self.assertRaises(ValueError):
                routes.remote_path_for_mount_mode(state)

    def test_non_strict_input_refused(self):
        for obj in (None, True, False, 1, [], {}, b"active"):
            with self.subTest(obj=obj), self.assertRaises(ValueError):
                routes.remote_path_for_mount_mode(obj)

    def test_url_points_to_expected_repo_and_v2_blob(self):
        url = routes.remote_url_for_mount_mode(
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop",
            "active")
        self.assertEqual(
            url,
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/"
            "develop/rclone/rclone-v2.conf.crypt")

    def test_url_legacy_preserved(self):
        url = routes.remote_url_for_mount_mode(
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop/",
            "legacy")
        self.assertTrue(url.endswith("/rclone/rclone.conf.crypt"))

    def test_url_rejects_other_repository_and_plain_http(self):
        for base in ("http://raw.githubusercontent.com/masQelec/cloud.masqelec/develop",
                     "https://raw.githubusercontent.com/other/cloud.masqelec/develop",
                     "https://example.org/myrepo",
                     "", None):
            with self.subTest(base=base), self.assertRaises(ValueError):
                routes.remote_url_for_mount_mode(base, "active")

    def test_url_rejects_query_fragment_and_injection(self):
        for url in (
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop?x=1",
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop#x",
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop\r\n",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                routes.remote_url_for_mount_mode(url, "active")

    def test_publish_paths_remain_distinct_and_explicit(self):
        self.assertEqual(routes.publication_destination("legacy"),
                         routes.LEGACY_REMOTE_PATH)
        self.assertEqual(routes.publication_destination("v2"),
                         routes.V2_REMOTE_PATH)
        for other in ("active", "prepared", "unsafe", None):
            with self.subTest(other=other), self.assertRaises(ValueError):
                routes.publication_destination(other)


if __name__ == "__main__":
    unittest.main()
