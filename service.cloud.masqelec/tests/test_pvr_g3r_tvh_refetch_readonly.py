"""G3-R read-only network inspector tests; all requests mocked."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, Mock
from contextlib import redirect_stdout
from io import StringIO

FILE = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3r_tvh_refetch_readonly.py"
spec = importlib.util.spec_from_file_location("pvr_g3r", FILE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class RefetchInspectionTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.network = {"uuid": M.TARGET, "networkname": "IPTV LOCAL"}
        self.node = {"uuid": M.TARGET, "props": [
            {"id": "url", "value": "file:///storage/.user/playlist.m3u"},
            {"id": "refetch_period", "value": 60},
        ]}

    def run_case(self):
        def getter(endpoint, params):
            self.calls.append(endpoint)
            return ({"total": 1, "entries": [self.network]}
                    if endpoint == "mpegts/network/grid" else
                    {"entries": [self.node]})
        with patch.object(M, "_request", side_effect=getter), \
             patch.object(M, "PLAYLIST", Mock(is_file=Mock(return_value=True), is_symlink=Mock(return_value=False))):
            with redirect_stdout(StringIO()) as buffer:
                code = M.inspect()
        return code, buffer.getvalue()

    def test_expected_local_network(self):
        status, output = self.run_case()
        self.assertEqual(status, 0)
        self.assertIn("REFETCH_PERIOD_MINUTES=60", output)
        self.assertIn("TRIGGER_EXECUTED=NO", output)
        self.assertEqual(self.calls, ["mpegts/network/grid", "idnode/load"])

    def test_unexpected_source_blocks(self):
        self.node["props"][0]["value"] = "http://secret.invalid/playlist.m3u"
        status, output = self.run_case()
        self.assertEqual(status, 2)
        self.assertIn("SOURCE_URL_STATUS=UNEXPECTED_OR_CHANGED", output)
        self.assertNotIn("secret.invalid", output)

    def test_unknown_period_blocks(self):
        self.node["props"][1]["value"] = None
        status, output = self.run_case()
        self.assertEqual(status, 2)
        self.assertIn("REFETCH_PERIOD_MINUTES=UNKNOWN", output)

    def test_ambiguous_network_blocks(self):
        def getter(endpoint, params):
            if endpoint == "mpegts/network/grid":
                return {"total": 2, "entries": [self.network, self.network]}
            raise AssertionError("unexpected idnode lookup")
        with patch.object(M, "_request", side_effect=getter), \
             patch.object(M, "PLAYLIST", Mock(
                 is_file=Mock(return_value=True),
                 is_symlink=Mock(return_value=False),
             )):
            with self.assertRaisesRegex(ValueError, "TARGET_NETWORK_AMBIGUOUS"):
                M.inspect()

    def test_write_endpoint_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNAPPROVED_ENDPOINT"):
            M._request("idnode/save", {})


if __name__ == "__main__":
    unittest.main()
