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
            return ("AUTH" if b"invalid-test-refresh-token" in raw else "OK")

        buf = io.StringIO()
        with mock.patch.object(pilot, "_rclone", return_value="/rclone"):
            with mock.patch.object(pilot, "_probe", side_effect=stub_probe):
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


if __name__ == "__main__":
    unittest.main()
