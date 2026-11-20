# -*- coding: utf-8 -*-
"""Readback CAS sintético; no HTTP real ni credenciales."""
import base64
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_publish_guard as publisher
from lib import rclone_two_mount_readback as readback
from test_rclone_mount_isolation import wrapped_conf


class ReadbackCasTests(unittest.TestCase):
    def setUp(self):
        self.canonical = wrapped_conf("crypt")
        self.key = b"K" * 32
        self.encrypted = publisher.encode_candidate(self.canonical, self.key)
        self.head = "b" * 40
        self.response = {
            "encoding": "base64",
            "sha": publisher.git_blob_sha(self.encrypted),
            "content": base64.b64encode(self.encrypted).decode("ascii"),
        }

    def check(self, **options):
        data = dict(expected_canonical=self.canonical,
                    expected_encrypted=self.encrypted,
                    readback_body=self.response,
                    key=self.key, expected_put_commit=self.head,
                    branch_head_before=self.head,
                    branch_head_after=self.head, put_accepted=True)
        data.update(options)
        return readback.confirm_readback(**data)

    def test_synthetic_cas_readback_only_not_release(self):
        self.assertEqual(self.check(), "verified_lab_only")

    def test_no_accepted_put_blocks(self):
        self.assertEqual(self.check(put_accepted=False),
                         "blocked_no_accepted_put")

    def test_put_commit_not_current_head_blocks(self):
        self.assertEqual(self.check(branch_head_before="c" * 40),
                         "blocked_remote_revision_drift")

    def test_head_moves_during_readback_blocks(self):
        self.assertEqual(self.check(branch_head_after="c" * 40),
                         "blocked_remote_revision_drift")

    def test_invalid_commit_sha_blocks(self):
        self.assertEqual(self.check(expected_put_commit="bad"),
                         "blocked_invalid_revision")

    def test_unauthenticated_mqc2_blocks(self):
        self.assertEqual(self.check(key=b"X" * 32),
                         "blocked_readback_auth_or_layout")

    def test_blob_sha_wrong_blocks(self):
        bad = dict(self.response, sha="c" * 40)
        self.assertEqual(self.check(readback_body=bad),
                         "blocked_readback_auth_or_layout")

    def test_ciphertext_changed_with_same_plaintext_blocks(self):
        other = publisher.encode_candidate(self.canonical, self.key)
        different = dict(self.response,
                         sha=publisher.git_blob_sha(other),
                         content=base64.b64encode(other).decode("ascii"))
        self.assertEqual(self.check(readback_body=different),
                         "blocked_remote_blob_mismatch")

    def test_valid_remote_different_oauth_content_blocks(self):
        changed = self.canonical.replace(
            b"refresh-users_library_1", b"rotated-refresh")
        new_encrypted = publisher.encode_candidate(changed, self.key)
        modified = dict(self.response,
                        sha=publisher.git_blob_sha(new_encrypted),
                        content=base64.b64encode(new_encrypted).decode())
        self.assertEqual(self.check(readback_body=modified),
                         "blocked_remote_blob_mismatch")

    def test_candidate_bytes_mismatch_blocked_even_if_blob_matches(self):
        changed = self.canonical.replace(
            b"access-users_library_1", b"changed-access")
        self.assertEqual(self.check(expected_canonical=changed),
                         "blocked_remote_content_mismatch")

    def test_invalid_expected_candidate_blocks(self):
        self.assertEqual(self.check(expected_canonical=b"junk"),
                         "blocked_readback_auth_or_layout")

    def test_no_secret_material_ever_returned(self):
        for case in (
                {}, {"key": b"X" * 32},
                {"branch_head_after": "a" * 40},
                {"put_accepted": False}):
            out = self.check(**case)
            self.assertNotIn("refresh", out)
            self.assertNotIn("users_library", out)
            self.assertNotIn("MQC2:", out)


if __name__ == "__main__":
    unittest.main()
