# -*- coding: utf-8 -*-
"""Regression gates for CLIENT v2 plan; no GitHub, rclone or Kodi required."""
import unittest
from unittest.mock import patch

from lib import rclone_two_mount_client_recovery as client


SHA = "a" * 40


class ClientRecoveryGates(unittest.TestCase):
    def _call(self, **overrides):
        args = dict(account_index=0, local_canonical=b"canonical",
                    local_account=b"account", remote_http_status=200,
                    remote_contents={"placeholder": True}, key=b"key",
                    auth_status="auth", release_authorized=True,
                    repository_head=SHA, observed_head=SHA)
        args.update(overrides)
        return client.prepare(**args)

    def test_disabled_even_when_auth(self):
        self.assertEqual(self._call(release_authorized=False)["status"],
                         "blocked_not_authorized")

    def test_only_auth_not_network_quota(self):
        for state in ("unavailable", "rate_limited", "ok", None):
            with self.subTest(state=state):
                self.assertEqual(self._call(auth_status=state)["status"],
                                 "blocked_not_auth")

    def test_only_two_accounts_exact_integer(self):
        for idx in (-1, 2, True, "0", None):
            with self.subTest(index=idx):
                self.assertEqual(self._call(account_index=idx)["status"],
                                 "blocked_account")

    def test_authenticated_head_must_be_stable(self):
        for head, observed in ((None, SHA), (SHA, "b"*40),
                               ("X"*40, "X"*40)):
            with self.subTest(head=head):
                self.assertEqual(self._call(repository_head=head,
                                            observed_head=observed)["status"],
                                 "blocked_repository_changed")

    def test_failed_or_missing_endpoint_no_fallback(self):
        for status in (0, 403, 404, 429, 500):
            with self.subTest(status=status):
                self.assertEqual(self._call(remote_http_status=status)["status"],
                                 "blocked_remote_unavailable")

    def test_rejects_bad_local_types(self):
        self.assertEqual(self._call(local_account="secret")["status"],
                         "blocked_local_invalid")

    @patch.object(client.policy, "validate_master_layout")
    @patch.object(client.plan, "account_snapshot")
    @patch.object(client.oauth, "_account")
    @patch.object(client.mqc2, "decode_remote_contents")
    @patch.object(client.policy, "tokens_from_master")
    @patch("lib.rclone_conf_merge.same_non_token_settings")
    def test_candidate_never_applied(self, same, merge, decode, account,
                                     account_snapshot, layout):
        same.return_value = True
        account.return_value = ("onedrive", {"refresh_token": "old"})
        decode.return_value = {"sha": "b"*40, "canonical": b"remote"}
        merge.return_value = b"merged"
        account_snapshot.side_effect = [b"account", b"newaccount"]
        result = self._call()
        self.assertEqual(result["status"], "candidate_requires_probe")
        self.assertEqual(result["baseline_account"], b"account")
        self.assertEqual(result["candidate_account"], b"newaccount")
        self.assertEqual(result["account_index"], 0)
        self.assertEqual(result["remote_sha"], "b"*40)

    @patch.object(client.policy, "validate_master_layout")
    def test_corrupt_canonical_fails_closed(self, layout):
        layout.side_effect = ValueError("unsafe")
        self.assertEqual(self._call()["status"],
                         "blocked_invalid_or_incompatible")

    def test_confirmation_requires_verified_probe_and_generations(self):
        candidate = {"status": "candidate_requires_probe"}
        for probe in ("auth", "unavailable", "rate_limited", None):
            self.assertEqual(client.confirm_probe(
                candidate, probe, baseline_unchanged=True,
                remote_head_unchanged=True),
                "blocked_probe_or_generation")
        self.assertEqual(client.confirm_probe(
            candidate, "ok", baseline_unchanged=True),
            "blocked_probe_or_generation")
        self.assertEqual(client.confirm_probe(
            candidate, "ok", baseline_unchanged=True,
            remote_head_unchanged=True),
            "probe_verified_requires_transactional_install")

    def test_confirmation_requires_candidate(self):
        self.assertEqual(client.confirm_probe({}, "ok"),
                         "blocked_no_candidate")


if __name__ == "__main__":
    unittest.main()
