# -*- coding: utf-8 -*-
"""OAuth policy, no Kodi, network, or actual secrets."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_token_policy as policy


def conf(refresh, access="a", expiry="2026-11-17T09:00:00Z", chunk="64M"):
    value = json.dumps({
        "access_token": access,
        "refresh_token": refresh,
        "expiry": expiry,
    }, sort_keys=True)
    return ("[cloud]\ntype = drive\nclient_id = x\nchunk_size = {}\ntoken = {}\n"
            .format(chunk, value)).encode("utf-8")


class RcloneTokenPolicyTests(unittest.TestCase):
    def test_ignore_access_and_expiry_churn(self):
        local = conf("valid", "access-two", "2026-11-17T12:00:00Z")
        old = conf("valid", "access-one", "2026-11-17T09:00:00Z")
        self.assertEqual(policy.stable_oauth_fingerprint(local),
                         policy.stable_oauth_fingerprint(old))
        self.assertFalse(policy.master_should_publish(local, old))

    def test_publish_rotated_refresh_when_newer(self):
        local = conf("rotated", "new", "2026-11-17T13:00:00Z")
        old = conf("older", "old", "2026-11-17T09:00:00Z")
        self.assertTrue(policy.master_should_publish(local, old))

    def test_master_rejects_older_credential(self):
        local = conf("older", expiry="2026-11-17T09:00:00Z")
        old = conf("rotated", expiry="2026-11-17T13:00:00Z")
        with self.assertRaisesRegex(ValueError, "anterior"):
            policy.master_should_publish(local, old)

    def test_master_can_publish_non_identity_settings(self):
        local = conf("same", chunk="128M")
        old = conf("same", chunk="64M")
        self.assertTrue(policy.master_should_publish(local, old))

    def test_master_rejects_identity_change(self):
        local = conf("same").replace(b"client_id = x", b"client_id = different")
        old = conf("same")
        with self.assertRaisesRegex(ValueError, "identidad"):
            policy.master_should_publish(local, old)

    def test_client_only_changes_failed_token(self):
        local = conf("bad")
        remote = conf("good")
        combined = policy.tokens_from_master(local, remote, ["cloud"])
        self.assertIn(b'"refresh_token": "good"', combined)
        self.assertNotIn(b'"refresh_token": "bad"', combined)
        self.assertEqual(policy.sections(local)["cloud"]["chunk_size"],
                         policy.sections(combined)["cloud"]["chunk_size"])

    def test_client_requires_new_refresh(self):
        with self.assertRaisesRegex(ValueError, "diferente"):
            policy.tokens_from_master(conf("same", "old"),
                                      conf("same", "new"), ["cloud"])

    def test_client_rejects_wrong_identity(self):
        local = conf("bad")
        remote = conf("good").replace(b"client_id = x", b"client_id = other")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            policy.tokens_from_master(local, remote, ["cloud"])

    def test_auth_failure_not_network_or_quota(self):
        self.assertTrue(policy.auth_failure(b"failed to refresh token: invalid_grant"))
        self.assertTrue(policy.auth_failure(b"oauth2: cannot fetch token"))
        self.assertFalse(policy.auth_failure(b"Failed to list: timeout"))
        self.assertFalse(policy.auth_failure(b"rate limit exceeded"))
        self.assertFalse(policy.auth_failure(b"permission denied"))

    def test_malformed_tokens_fail_closed(self):
        bad = b'[cloud]\ntype = drive\ntoken = {not-json}\n'
        with self.assertRaisesRegex(ValueError, "JSON"):
            policy.oauth_tokens(bad)


if __name__ == "__main__":
    unittest.main()
