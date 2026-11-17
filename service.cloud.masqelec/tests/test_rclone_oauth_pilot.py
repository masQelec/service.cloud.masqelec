# -*- coding: utf-8 -*-
"""El piloto no modifica rclone.conf real ni requiere Kodi o red."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import rclone_oauth_pilot as pilot


def _config(refresh="live-refresh"):
    token = json.dumps({
        "access_token": "live-access",
        "refresh_token": refresh,
        "expiry": "2026-11-18T10:00:00Z",
    })
    return ("[testing]\ntype = drive\nclient_id = dummy\ntoken = " +
            token + "\n").encode("utf-8")


class OAuthPilotTests(unittest.TestCase):
    def test_fake_client_invalidates_only_copy(self):
        original = _config()
        broken = pilot._invalidate_for_test(original, "testing")
        self.assertIn(b"invalid-test-refresh-token", broken)
        self.assertIn(b"live-refresh", original)
        self.assertNotIn(b"invalid-test-refresh-token", original)
        self.assertNotEqual(original, broken)

    def test_simulation_uses_only_temporary_copies(self):
        original = _config()
        def stub_probe(binary, name, path):
            with open(path, "rb") as f:
                raw = f.read()
            if b"invalid-test-refresh-token" in raw:
                return ("AUTH", "AUTH", 1)
            return ("OK", "OK", 0)

        buf = io.StringIO()
        with mock.patch.object(pilot, "_rclone", return_value="/rclone"):
            with mock.patch.object(pilot, "_probe_details", side_effect=stub_probe):
                with contextlib.redirect_stdout(buf):
                    result = pilot._client_simulation(original)
        self.assertEqual(result, 0)
        self.assertIn("SIMULATION=PASS", buf.getvalue())
        self.assertNotIn("live-refresh", buf.getvalue())
        self.assertNotIn("live-access", buf.getvalue())

    def test_no_token_or_secret_in_master_report(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pilot._master_check(_config("new-refresh"), _config("old-refresh"))
        report = buf.getvalue()
        self.assertIn("MASTER_PUBLISH_DECISION=CHANGED", report)
        self.assertNotIn("refresh", report)
        self.assertNotIn("access", report)

    def test_read_does_not_modify_source(self):
        with tempfile.TemporaryDirectory() as temp:
            file = os.path.join(temp, "rclone.conf")
            original = _config()
            with open(file, "wb") as stream:
                stream.write(original)
            self.assertEqual(pilot._read(file), original)
            self.assertEqual(open(file, "rb").read(), original)


    def test_classifies_failure_without_exposing_secret(self):
        cases = [
            (b"oauth2: cannot fetch token: invalid_grant", "AUTH"),
            (b"Failed to list: directory not found", "REMOTE_PATH"),
            (b"network is unreachable", "NETWORK"),
            (b"429 Too Many Requests", "RATE_LIMIT"),
            (b"403 forbidden", "PERMISSION"),
            (b"certificate verify failed", "TLS"),
            (b"private information: MY_SECRET", "UNCLASSIFIED"),
        ]
        for stderr, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(pilot._classify_failure(stderr), expected)

    def test_inconclusive_includes_local_baseline_reason_no_secret(self):
        original = _config()
        seen = []

        def stub_probe(binary, name, path):
            with open(path, "rb") as stream:
                raw = stream.read()
            seen.append(path)
            if b"invalid-test-refresh-token" in raw:
                return ("AUTH", "AUTH", 1)
            if os.path.basename(path) == "candidate.conf":
                return ("UNKNOWN", "REMOTE_PATH", 3)
            return ("OK", "OK", 0)

        buf = io.StringIO()
        with mock.patch.object(pilot, "_rclone", return_value="/rclone"):
            with mock.patch.object(pilot, "_probe_details", side_effect=stub_probe):
                with contextlib.redirect_stdout(buf):
                    result = pilot._client_simulation(original, local=original)
        self.assertEqual(result, 2)
        report = buf.getvalue()
        self.assertIn("SIMULATED_RECOVERY_REASON=REMOTE_PATH", report)
        self.assertIn("LOCAL_COPY_BASELINE=OK", report)
        self.assertNotIn("live-refresh", report)
        self.assertNotIn("live-access", report)
        self.assertEqual(len(seen), 3)
        self.assertTrue(all("/tmp/" in path for path in seen))

    def test_remote_index_invalid_returns_no_sensitive_data(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = pilot._client_simulation(_config(), remote_index=99)
        self.assertEqual(result, 2)
        self.assertIn("SIMULATION=INVALID_REMOTE_INDEX", buf.getvalue())


if __name__ == "__main__":
    unittest.main()
