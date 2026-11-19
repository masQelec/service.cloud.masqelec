# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
from lib import rclone_two_mount_client_runtime as runtime

SHA = "a" * 40


class ClientRuntimeGates(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.sources = (b"canonical", (b"account-1", b"account-2"))

    def _sources(self):
        self.calls.append("sources")
        return self.sources

    def _head(self):
        self.calls.append("head")
        return SHA

    def _get(self, path):
        self.calls.append("get:" + path)
        return 200, {"mock": "response"}

    def _probe(self, index, candidate):
        self.calls.append("probe")
        return "ok"

    def run_case(self, **kwargs):
        args = dict(account_index=0, auth_status="auth",
                    read_sources=self._sources, head=self._head,
                    get=self._get, probe=self._probe, key=b"key",
                    release_authorized=True)
        args.update(kwargs)
        return runtime.verify_once(**args)

    def test_disabled_no_callbacks(self):
        self.assertEqual(self.run_case(release_authorized=False),
                         "blocked_not_authorized")
        self.assertEqual(self.calls, [])

    def test_no_auth_no_callbacks(self):
        for status in ("unavailable", "rate_limited", "ok"):
            self.assertEqual(self.run_case(auth_status=status),
                             "blocked_not_auth")
        self.assertEqual(self.calls, [])

    def test_invalid_index_no_callbacks(self):
        self.assertEqual(self.run_case(account_index=True), "blocked_account")
        self.assertEqual(self.calls, [])

    def test_no_dependencies_no_callbacks(self):
        self.assertEqual(self.run_case(probe=None), "blocked_dependency")
        self.assertEqual(self.calls, [])

    @patch.object(runtime.recovery, "prepare")
    @patch.object(runtime.recovery, "confirm_probe")
    def test_candidate_is_probed_and_rechecked_no_install(self, gate, prepare):
        prepare.return_value = {
            "status": "candidate_requires_probe",
            "candidate_account": b"candidate"
        }
        gate.return_value = "probe_verified_requires_transactional_install"
        self.assertEqual(self.run_case(),
                         "probe_verified_requires_transactional_install")
        self.assertEqual(self.calls, [
            "sources", "head", "get:rclone/rclone-v2.conf.crypt",
            "head", "probe", "sources", "head"])
        gate.assert_called_once()
        self.assertTrue(gate.call_args.kwargs["baseline_unchanged"])
        self.assertTrue(gate.call_args.kwargs["remote_head_unchanged"])

    @patch.object(runtime.recovery, "prepare")
    def test_remote_missing_never_probes(self, prepare):
        prepare.return_value = {"status": "blocked_remote_unavailable"}
        self.assertEqual(self.run_case(), "blocked_remote_unavailable")
        self.assertNotIn("probe", self.calls)

    @patch.object(runtime.recovery, "prepare")
    def test_bad_probe_fails_closed(self, prepare):
        prepare.return_value = {"status": "candidate_requires_probe",
                                "candidate_account": b"candidate"}
        self.assertEqual(self.run_case(probe=lambda i, candidate: "auth"),
                         "blocked_probe_or_generation")

    @patch.object(runtime.recovery, "prepare")
    @patch.object(runtime.recovery, "confirm_probe")
    def test_verified_candidate_handoff_only_on_explicit_request(
            self, gate, prepare):
        prepared = {"status": "candidate_requires_probe",
                    "candidate_account": b"secret-candidate",
                    "account_index": 0}
        prepare.return_value = prepared
        gate.return_value = "probe_verified_requires_transactional_install"
        outcome = self.run_case(return_candidate=True)
        self.assertEqual(outcome["status"], "candidate_probe_verified")
        self.assertIs(outcome["prepared"], prepared)
        gate.return_value = "blocked_probe_or_generation"
        self.assertEqual(self.run_case(return_candidate=True),
                         "blocked_probe_or_generation")

    def test_transport_error_is_not_auth(self):
        def crash(path):
            raise OSError("unavailable")
        self.assertEqual(self.run_case(get=crash), "blocked_runtime_error")


if __name__ == "__main__":
    unittest.main()
