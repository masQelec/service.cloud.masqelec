# -*- coding: utf-8 -*-
"""Reconciliación pura 2 FUSE / legacy MQC2: no red, ni systemd, ni disco."""
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import rclone_two_mount_oauth as coord
from lib import rclone_mount_isolation as isolation
from lib import rclone_token_policy as policy
from lib import rclone_conf_merge as merge
from test_rclone_mount_isolation import wrapped_conf


class TwoMountOauthTests(unittest.TestCase):
    def setUp(self):
        self.canonical = wrapped_conf("crypt")
        self.published = self.canonical
        self.sources = (
            isolation.select_remote(self.canonical, "users_library_1"),
            isolation.select_remote(self.canonical, "users_library_2"),
        )

    def _rotated(self, idx, refresh):
        raw = self.sources[idx]
        previous = (b"refresh-users_library_1" if idx == 0 else
                    b"refresh-users_library_2")
        return raw.replace(previous, refresh)

    def test_same_two_accounts_no_publication(self):
        result = coord.prepare_master(
            self.canonical, self.sources, self.published)
        self.assertEqual(result["status"], "unchanged")
        self.assertIsNone(result["candidate"])
        self.assertEqual(result["changed_names"], ())

    def test_one_account_rotates_google_and_crypt_unchanged(self):
        sources = (self._rotated(0, b"new-refresh-one"), self.sources[1])
        result = coord.prepare_master(self.canonical, sources, self.published)
        self.assertEqual(result["status"], "candidate_requires_probe")
        self.assertEqual(result["changed_names"], ("one_a",))
        candidate = result["candidate"]
        self.assertEqual(len(policy.sections(candidate)), 6)
        self.assertEqual(policy.validate_master_layout(candidate),
                         policy.validate_master_layout(self.canonical))
        before, after = policy.sections(self.canonical), policy.sections(candidate)
        for name in ("users_library_1", "users_library_2", "updater", "logs"):
            self.assertEqual(after[name], before[name])
        self.assertEqual(policy.oauth_tokens(candidate)["one_a"]["refresh_token"],
                         "new-refresh-one")
        self.assertEqual(policy.oauth_tokens(candidate)["one_b"],
                         policy.oauth_tokens(self.canonical)["one_b"])
        self.assertTrue(merge.same_non_token_settings(candidate, self.canonical))
        self.assertTrue(policy.master_should_publish(candidate, self.published))

    def test_second_account_rotates_alone(self):
        result = coord.prepare_master(
            self.canonical,
            (self.sources[0], self._rotated(1, b"new-refresh-two")),
            self.published)
        self.assertEqual(result["changed_names"], ("one_b",))
        self.assertEqual(policy.oauth_tokens(result["candidate"])["one_a"],
                         policy.oauth_tokens(self.canonical)["one_a"])

    def test_two_account_rotation_preserves_legacy_mqc2_layout(self):
        sources = (self._rotated(0, b"new-refresh-one"),
                   self._rotated(1, b"new-refresh-two"))
        result = coord.prepare_master(self.canonical, sources, self.published)
        self.assertEqual(result["changed_names"], ("one_a", "one_b"))
        candidate = result["candidate"]
        self.assertEqual(policy.oauth_provider_counts(candidate),
                         {"onedrive": 2, "drive": 2})
        self.assertEqual(len(policy.sections(candidate)), 6)
        self.assertIn(b"filename_encryption = off", candidate)
        self.assertEqual(policy.sections(candidate)["users_library_1"],
                         policy.sections(self.canonical)["users_library_1"])

    def test_access_token_only_churn_never_publishes(self):
        local = self.sources[0].replace(
            b"access-users_library_1", b"new-access-only")
        self.assertEqual(coord.prepare_master(
            self.canonical, (local, self.sources[1]), self.published)["status"],
            "unchanged")

    def test_diff_master_vs_mqc2_blocks_unordered_token_promotion(self):
        published = self.canonical.replace(
            b"refresh-users_library_1", b"other-published-refresh")
        result = coord.prepare_master(
            self.canonical,
            (self._rotated(0, b"new-local-refresh"), self.sources[1]),
            published)
        self.assertEqual(result["status"], "published_baseline_diverged")
        self.assertIsNone(result["candidate"])

    def test_google_drive_refresh_mismatch_also_blocks(self):
        published = self.canonical.replace(
            b"refresh-updater", b"new-google-refresh")
        result = coord.prepare_master(
            self.canonical, self.sources, published)
        self.assertEqual(result["status"], "published_baseline_diverged")

    def test_static_change_in_crypt_snapshot_blocked(self):
        local = self.sources[0].replace(
            b"filename_encryption = off", b"filename_encryption = standard")
        with self.assertRaisesRegex(ValueError, "crypt"):
            coord.prepare_master(self.canonical, (local, self.sources[1]),
                                 self.published)

    def test_crypt_password_change_blocked_even_same_oauth(self):
        local = self.sources[0].replace(
            b"password = OBFUSCATED_TEST_VALUE",
            b"password = OTHER_VALUE")
        with self.assertRaisesRegex(ValueError, "crypt"):
            coord.prepare_master(self.canonical, (local, self.sources[1]),
                                 self.published)

    def test_provider_identity_change_blocked(self):
        local = self.sources[0].replace(
            b"drive_id = users_library_1-id", b"drive_id = other-drive")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            coord.prepare_master(self.canonical, (local, self.sources[1]),
                                 self.published)

    def test_wrong_account_order_blocked(self):
        with self.assertRaises(ValueError):
            coord.prepare_master(
                self.canonical, self.sources[::-1], self.published)

    def test_cross_account_oauth_leak_blocked(self):
        leaked = self.sources[0] + self.sources[1]
        with self.assertRaises(ValueError):
            coord.prepare_master(
                self.canonical, (leaked, self.sources[1]), self.published)

    def test_unexpected_static_option_published_blocks(self):
        published = self.published.replace(
            b"remote = one_a:library", b"remote = one_b:library")
        with self.assertRaisesRegex(ValueError, "opciones"):
            coord.prepare_master(self.canonical, self.sources, published)

    def test_wrong_snapshot_count_blocked(self):
        with self.assertRaisesRegex(ValueError, "dos snapshots"):
            coord.prepare_master(self.canonical, self.sources[:1],
                                 self.published)

    def test_duplicate_auth_identity_across_accounts_blocked(self):
        baseline = self.canonical.replace(
            b"remote = one_b:library", b"remote = one_a:library")
        copied = (isolation.select_remote(baseline, "users_library_1"),
                  isolation.select_remote(baseline, "users_library_2"))
        with self.assertRaisesRegex(ValueError, "comparten"):
            coord.prepare_master(baseline, copied, baseline)

    def test_probe_gate_requires_all_changed_remotes_successful(self):
        prepared = coord.prepare_master(
            self.canonical,
            (self._rotated(0, b"new-one"), self._rotated(1, b"new-two")),
            self.published)
        self.assertEqual(
            coord.probe_gate(prepared, {"one_a": "ok", "one_b": "ok"}),
            "revalidate_sources_before_publish")
        for value in ("auth", "unavailable", "rate_limited", "timeout"):
            self.assertEqual(
                coord.probe_gate(prepared, {"one_a": "ok", "one_b": value}),
                "probe_failed")
        self.assertEqual(coord.probe_gate(prepared, {"one_a": "ok"}),
                         "probe_failed")
        self.assertEqual(coord.probe_gate(
            {"status": "unchanged"}, {"one_a": "ok"}), "blocked")

    def test_client_must_observe_explicit_auth_error(self):
        broken = self._rotated(0, b"old-broken")
        result = coord.prepare_client(
            self.canonical, 0, broken, confirmed_auth_error=False)
        self.assertEqual(result["status"], "no_explicit_oauth_error")
        self.assertIsNone(result["candidate"])

    def test_client_recovers_only_failed_account_as_uninstalled_candidate(self):
        local = self._rotated(0, b"old-broken")
        result = coord.prepare_client(
            self.canonical, 0, local, confirmed_auth_error=True)
        self.assertEqual(result["status"],
                         "candidate_requires_probe_and_safe_apply")
        self.assertEqual(result["remote"], "one_a")
        target = result["candidate"]
        self.assertEqual(set(policy.sections(target)),
                         set(policy.sections(local)))
        self.assertTrue(merge.same_non_token_settings(target, local))
        self.assertEqual(policy.oauth_tokens(target)["one_a"]["refresh_token"],
                         "refresh-users_library_1")
        self.assertNotIn(b"[one_b]", target)
        self.assertNotIn(b"[updater]", target)

    def test_client_same_refresh_different_access_allows_probe_only(self):
        local = self.sources[0].replace(
            b"access-users_library_1", b"broken-access")
        result = coord.prepare_client(
            self.canonical, 0, local, confirmed_auth_error=True)
        self.assertEqual(result["status"],
                         "candidate_requires_probe_and_safe_apply")
        self.assertEqual(policy.oauth_tokens(result["candidate"])["one_a"],
                         policy.oauth_tokens(self.canonical)["one_a"])

    def test_client_identical_master_token_has_no_alternative(self):
        result = coord.prepare_client(
            self.canonical, 0, self.sources[0], confirmed_auth_error=True)
        self.assertEqual(result["status"], "no_alternative")

    def test_client_no_cross_account_password_changes(self):
        local = self.sources[1].replace(
            b"password = OBFUSCATED_TEST_VALUE",
            b"password = TAMPERED")
        with self.assertRaisesRegex(ValueError, "crypt"):
            coord.prepare_client(
                self.canonical, 1, local, confirmed_auth_error=True)

    def test_client_bad_oauth_json_refused(self):
        broken = self.sources[0].replace(
            b'"refresh_token": "refresh-users_library_1"',
            b'"refresh_token": {BROKEN')
        with self.assertRaisesRegex(ValueError, "JSON"):
            coord.prepare_client(self.canonical, 0, broken, True)

    def test_no_files_modified_by_pure_policy(self):
        before = (bytes(self.canonical), bytes(self.sources[0]),
                  bytes(self.sources[1]))
        coord.prepare_master(self.canonical, self.sources, self.published)
        coord.prepare_client(self.canonical, 0, self.sources[0], True)
        self.assertEqual(before, (self.canonical, *self.sources))


if __name__ == "__main__":
    unittest.main()
