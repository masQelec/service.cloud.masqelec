# -*- coding: utf-8 -*-
"""Conciliación OAuth de rollback: pruebas puras con secretos ficticios."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_token_rollback as rollback
from lib import rclone_token_policy as policy
from lib import rclone_conf_merge as merge
from test_rclone_mount_isolation import wrapped_conf


def rotate(raw, section, refresh=None, access=None):
    options = policy.sections(raw)
    tok = options[section]["token"]
    value = json.loads(tok)
    if refresh is not None:
        value["refresh_token"] = refresh
    if access is not None:
        value["access_token"] = access
    return raw.replace(tok.encode(), json.dumps(value).encode(), 1)


class TokenRollbackTests(unittest.TestCase):
    def setUp(self):
        self.canonical = wrapped_conf("crypt")
        self.a = plan.account_snapshot(self.canonical, 0)
        self.b = plan.account_snapshot(self.canonical, 1)

    def reconcile(self, current=None, a=None, b=None, baseline=None):
        return rollback.reconcile_canonical_for_rollback(
            self.canonical if baseline is None else baseline,
            self.canonical if current is None else current,
            self.a if a is None else a,
            self.b if b is None else b)

    def test_unchanged_remotes_return_original_config(self):
        self.assertEqual(self.reconcile(), self.canonical)

    def test_one_rotated_refresh_is_preserved_at_rollback(self):
        a = rotate(self.a, "one_a", refresh="new-private-A")
        result = self.reconcile(a=a)
        self.assertEqual(policy.oauth_tokens(result)["one_a"]["refresh_token"],
                         "new-private-A")
        self.assertEqual(policy.oauth_tokens(result)["one_b"],
                         policy.oauth_tokens(self.canonical)["one_b"])

    def test_both_rotated_refresh_tokens_rejoin_correct_accounts(self):
        a = rotate(self.a, "one_a", refresh="new-private-A")
        b = rotate(self.b, "one_b", refresh="new-private-B")
        result = self.reconcile(a=a, b=b)
        self.assertEqual(policy.oauth_tokens(result)["one_a"]["refresh_token"],
                         "new-private-A")
        self.assertEqual(policy.oauth_tokens(result)["one_b"]["refresh_token"],
                         "new-private-B")

    def test_google_token_change_preserved_from_current(self):
        current = rotate(self.canonical, "updater", refresh="google-refreshed")
        result = self.reconcile(current=current,
                                a=rotate(self.a, "one_a", refresh="one-new"))
        self.assertEqual(policy.oauth_tokens(result)["updater"]["refresh_token"],
                         "google-refreshed")
        self.assertEqual(policy.oauth_tokens(result)["one_a"]["refresh_token"],
                         "one-new")

    def test_other_google_token_unchanged(self):
        output = self.reconcile(a=rotate(self.a, "one_a", refresh="one-new"))
        self.assertEqual(policy.oauth_tokens(output)["logs"],
                         policy.oauth_tokens(self.canonical)["logs"])

    def test_canonical_one_drive_concurrent_refresh_blocks(self):
        current = rotate(self.canonical, "one_a", refresh="other-process")
        with self.assertRaisesRegex(ValueError, "canónico cambiado"):
            self.reconcile(current=current)

    def test_canonical_access_token_only_change_also_blocks(self):
        current = rotate(self.canonical, "one_b", access="other-access")
        with self.assertRaisesRegex(ValueError, "canónico cambiado"):
            self.reconcile(current=current)

    def test_mismatch_one_drive_identity_blocks(self):
        a = self.a.replace(b"drive_type = personal", b"drive_type = business")
        with self.assertRaisesRegex(ValueError, "Identidad crypt"):
            self.reconcile(a=a)

    def test_swapped_snapshots_block(self):
        with self.assertRaises(ValueError):
            self.reconcile(a=self.b, b=self.a)

    def test_crypt_password_mismatch_blocks(self):
        a = self.a.replace(b"OBFUSCATED_TEST_VALUE", b"MODIFIED_CRYPT")
        with self.assertRaisesRegex(ValueError, "Identidad crypt"):
            self.reconcile(a=a)

    def test_crypt_remote_change_blocks(self):
        a = self.a.replace(b"remote = one_a:library",
                           b"remote = one_b:library")
        with self.assertRaises(ValueError):
            self.reconcile(a=a)

    def test_unexpected_additional_remote_blocks(self):
        a = self.a + b"\n[extra]\ntype = local\n"
        with self.assertRaises(ValueError):
            self.reconcile(a=a)

    def test_invalid_refresh_block(self):
        a = rotate(self.a, "one_a", refresh="")
        with self.assertRaisesRegex(ValueError, "refresh_token"):
            self.reconcile(a=a)

    def test_malformed_oauth_json_block(self):
        original_token = policy.sections(self.a)["one_a"]["token"].encode()
        a = self.a.replace(original_token, b"INVALID_JSON_FOR_TEST", 1)
        self.assertNotEqual(a, self.a)
        with self.assertRaises(ValueError):
            self.reconcile(a=a)

    def test_changed_non_token_canonical_setting_blocks(self):
        current = self.canonical.replace(
            b"filename_encryption = off", b"filename_encryption = standard")
        with self.assertRaisesRegex(ValueError, "configuración canónica"):
            self.reconcile(current=current)

    def test_same_non_token_options_and_no_github_or_systemd(self):
        a = rotate(self.a, "one_a", refresh="new-private-A")
        result = self.reconcile(a=a)
        self.assertTrue(merge.same_non_token_settings(self.canonical, result))
        self.assertNotIn(b"new-private-A", self.canonical)
        source = (Path(__file__).resolve().parents[1] /
                  "lib/rclone_two_mount_token_rollback.py").read_text()
        self.assertNotIn("subprocess.run(", source)
        self.assertNotIn("subprocess", source)
        self.assertNotIn("urllib", source)


if __name__ == "__main__":
    unittest.main()
