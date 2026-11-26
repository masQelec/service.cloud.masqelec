# -*- coding: utf-8 -*-
"""Verificación OAuth y CAS GitHub v2 en mocks, sin red real."""
import base64
import json
import os
from pathlib import Path
import sys
import subprocess
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import chacha_pure
from lib import rclone_two_mount_verify as verifier
from lib import rclone_two_mount_publish_guard as publisher
from lib import rclone_two_mount_plan as plan
from lib import rclone_token_policy as policy
from test_rclone_mount_isolation import wrapped_conf


class OAuthV2RealProbeTests(unittest.TestCase):
    def setUp(self):
        self.canonical = wrapped_conf("crypt")
        self.source = plan.account_snapshot(self.canonical, 0)
        self.calls = []

    def _runner(self, status=0, simulated_stderr=b"", transform=None):
        def run(cmd, stdout, stderr, timeout, check):
            self.calls.append(cmd)
            self.assertEqual(cmd[1], "lsf")
            self.assertEqual(cmd[2], "one_a:")
            self.assertEqual(cmd[3], "--config")
            self.assertEqual(timeout, 45)
            path = cmd[4]
            self.assertTrue(path.startswith("/tmp/"))
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            self.assertEqual(Path(path).read_bytes(), self.source)
            if transform is not None:
                Path(path).write_bytes(transform(self.source))
            # 'stderr' es el descriptor subprocess.PIPE (-1), NO el
            # mensaje simulado que debe clasificar la función probada.
            self.assertEqual(stderr, subprocess.PIPE)
            return types.SimpleNamespace(
                returncode=status, stderr=simulated_stderr
            )
        return run

    def test_success_checks_actual_temporary_file(self):
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner())
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["post_probe"], self.source)
        self.assertFalse(result["refresh_rotated"])
        self.assertEqual(len(self.calls), 1)

    def test_probe_temp_refresh_renewal_is_detected_not_discarded(self):
        modified = self.source.replace(b"refresh-users_library_1",
                                       b"rotated-after-probe")
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner(transform=lambda raw: modified))
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["refresh_rotated"])
        self.assertEqual(result["post_probe"], modified)
        self.assertNotEqual(result["post_probe"], self.source)

    def test_failed_auth_classified_without_promoting_tokens(self):
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner(1, b"oauth2: invalid_grant"))
        self.assertEqual(result["status"], "auth")
        self.assertIsNone(result["post_probe"])

    def test_failed_quota_never_becomes_auth_error(self):
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner(1, b"HTTP 429 throttled"))
        self.assertEqual(result["status"], "rate_limited")

    def test_failed_network_never_becomes_auth_error(self):
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner(1, b"Network is unreachable"))
        self.assertEqual(result["status"], "unavailable")

    def test_success_but_crypt_password_changed_blocks(self):
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner(transform=lambda raw:
                raw.replace(b"password = OBFUSCATED_TEST_VALUE",
                            b"password = OTHER_VALUE")))
        self.assertEqual(result["status"], "tampered")
        self.assertIsNone(result["post_probe"])

    def test_success_but_token_removed_blocks(self):
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone",
            self._runner(transform=lambda raw:
                raw.replace(b"refresh-users_library_1", b"")))
        self.assertEqual(result["status"], "tampered")

    def test_wrong_account_snapshot_blocks_before_runner(self):
        second = plan.account_snapshot(self.canonical, 1)
        with self.assertRaises(ValueError):
            verifier.probe_one(self.canonical, 0, second,
                               "/usr/bin/rclone", self._runner())
        self.assertEqual(len(self.calls), 0)

    def test_rclone_binary_path_must_be_absolute(self):
        with self.assertRaises(ValueError):
            verifier.probe_one(self.canonical, 0, self.source,
                               "rclone", self._runner())

    def test_timeout_is_unavailable(self):
        import subprocess
        def runner(cmd, **kw):
            raise subprocess.TimeoutExpired(cmd, 45)
        result = verifier.probe_one(
            self.canonical, 0, self.source, "/usr/bin/rclone", runner)
        self.assertEqual(result["status"], "unavailable")


class OAuthV2StrictPublicationTests(unittest.TestCase):
    def setUp(self):
        self.canonical = wrapped_conf("crypt")
        self.key = b"K" * 32
        self.cipher = publisher.encode_candidate(self.canonical, self.key)
        self.sha = publisher.git_blob_sha(self.cipher)
        self.response = {
            "sha": self.sha,
            "encoding": "base64",
            "content": base64.b64encode(self.cipher).decode("ascii"),
        }

    def test_roundtrip_mqc2_preserves_six_sections(self):
        out = publisher.decode_remote_contents(self.response, self.key)
        self.assertEqual(out["canonical"], self.canonical)
        self.assertEqual(out["sha"], self.sha)
        self.assertEqual(policy.oauth_provider_counts(out["canonical"]),
                         {"onedrive": 2, "drive": 2})
        self.assertIn(b"filename_encryption = off", out["canonical"])

    def test_git_sha_mismatch_blocks_before_decrypt(self):
        bad = dict(self.response, sha="0"*40)
        with self.assertRaisesRegex(ValueError, "SHA GH"):
            publisher.decode_remote_contents(bad, self.key)

    def test_modified_mqc2_authentication_fails(self):
        damaged = bytearray(self.cipher)
        damaged[-8] = ord("0") if damaged[-8] != ord("0") else ord("1")
        response = dict(self.response,
                        sha=publisher.git_blob_sha(bytes(damaged)),
                        content=base64.b64encode(damaged).decode("ascii"))
        with self.assertRaises(ValueError):
            publisher.decode_remote_contents(response, self.key)

    def test_wrong_device_key_fails(self):
        with self.assertRaises(ValueError):
            publisher.decode_remote_contents(self.response, b"X"*32)

    def test_unknown_gh_encoding_blocks(self):
        bad = dict(self.response, encoding="none")
        with self.assertRaisesRegex(ValueError, "base64"):
            publisher.decode_remote_contents(bad, self.key)

    def test_put_requires_all_permissions(self):
        calls = []
        def request(*args):
            calls.append(args)
            return 200, {}
        for perms in (
            {},
            {"release_authorized": True},
            {"release_authorized": True, "sources_revalidated": True},
            {"release_authorized": True, "remote_authenticated": True},
        ):
            self.assertEqual(publisher.strict_put(
                "fake", self.cipher, self.sha, request, branch="21", **perms), "blocked")
        self.assertEqual(calls, [])

    def test_put_includes_expected_sha_and_no_secrets_in_commit_message(self):
        calls = []
        def request(token, dest, payload):
            calls.append((token, dest, payload))
            return 200, {"content":{"sha": publisher.git_blob_sha(
                self.cipher)}}
        status = publisher.strict_put(
            "fake", self.cipher, self.sha, request,
            branch="21", release_authorized=True,
            sources_revalidated=True,
            remote_authenticated=True,
        )
        self.assertEqual(status, "accepted_requires_remote_confirmation")
        self.assertEqual(len(calls), 1)
        token, path, data = calls[0]
        self.assertEqual(token, "fake")
        self.assertEqual(path, "rclone/rclone.conf.crypt")
        self.assertEqual(data["branch"], "21")
        self.assertEqual(data["sha"], self.sha)
        self.assertNotIn("refresh", data["message"])
        self.assertEqual(base64.b64decode(data["content"]), self.cipher)

    def test_put_conflict_409_no_retry(self):
        calls = []
        def request(*args):
            calls.append(args)
            return 409, "conflict"
        self.assertEqual(publisher.strict_put(
            "fake", self.cipher, self.sha, request,
            branch="21", release_authorized=True, sources_revalidated=True,
            remote_authenticated=True), "remote_conflict_no_retry")
        self.assertEqual(len(calls), 1)

    def test_put_422_no_retry(self):
        calls = []
        def request(*args):
            calls.append(args)
            return 422, "conflict"
        self.assertEqual(publisher.strict_put(
            "fake", self.cipher, self.sha, request,
            branch="21", release_authorized=True, sources_revalidated=True,
            remote_authenticated=True), "remote_rejected_no_retry")
        self.assertEqual(len(calls), 1)

    def test_put_does_not_guess_expected_sha(self):
        with self.assertRaisesRegex(ValueError, "SHA esperado"):
            publisher.strict_put(
                "fake", self.cipher, None,
                lambda *args: (200, {}),
                branch="21", release_authorized=True, sources_revalidated=True,
                remote_authenticated=True,
            )

    def test_invalid_local_layout_never_encrypted_for_upload(self):
        with self.assertRaisesRegex(ValueError, "Inventario"):
            publisher.encode_candidate(
                self.canonical.replace(b"type = drive", b"type = alias", 1),
                self.key
            )

    def test_race_checked_against_expected_sha_only(self):
        expected = "a"*40
        seen = []
        def request(token, path, payload):
            seen.append(payload["sha"])
            return 409, None
        publisher.strict_put("fake", self.cipher, expected, request,
            branch="21", release_authorized=True, sources_revalidated=True,
            remote_authenticated=True)
        self.assertEqual(seen, [expected])
