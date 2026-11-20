"""G3-M purely read-only integration checks (network mocked)."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "lib"))
PATH = BASE / "tools" / "pvr_g3m_tvh_readonly_integration.py"
SPEC = importlib.util.spec_from_file_location("pvr_g3m_tvh_readonly_integration", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

PLAYLIST = '#EXTM3U\n#EXTINF:-1 group-title="A",One\nurl1\n#EXTINF:-1 group-title="B",Two\nurl2\n'


class ReadonlyIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tags = {"total": 3, "entries": [
            {"uuid": "a", "name": "A", "internal": False},
            {"uuid": "b", "name": "B", "internal": False},
            {"uuid": "obsolete", "name": "Old", "internal": False},
        ]}
        self.channels = {"total": 2, "entries": [
            {"uuid": "1", "tags": ["a"]}, {"uuid": "2", "tags": ["b"]}
        ]}

    def probe(self, on_read=None):
        calls = []
        def fake_grid(endpoint):
            calls.append(endpoint)
            if on_read:
                on_read(len(calls))
            return self.tags.copy() if endpoint == "channeltag/grid" else self.channels.copy()
        with patch.object(M, "_read_m3u", return_value=PLAYLIST), \
             patch.object(M, "_grid", side_effect=fake_grid):
            with redirect_stdout(StringIO()) as buf:
                result = M.diagnose()
        return result, buf.getvalue(), calls

    def test_readonly_reports_protected_old_tag(self):
        code, output, calls = self.probe()
        self.assertEqual(code, 0)
        self.assertEqual(calls, ["channeltag/grid", "channel/grid"] * 2)
        self.assertIn("UNOWNED_OR_PROTECTED_EMPTY=1", output)
        self.assertIn("API_WRITE_EXECUTED=NO", output)

    def test_snapshot_drift_blocks(self):
        def drift(i):
            if i == 3:
                self.tags = {"total": 2, "entries": self.tags["entries"][:2]}
        with self.assertRaisesRegex(M.PlanBlocked, "INVENTORY_DRIFT"):
            self.probe(on_read=drift)

    def test_partial_grid_blocks(self):
        self.tags["total"] = 5
        with self.assertRaisesRegex(M.PlanBlocked, "INCOMPLETE_INVENTORY"):
            self.probe()

    def test_disallow_write_endpoints(self):
        with self.assertRaisesRegex(ValueError, "ENDPOINT_NOT_ALLOWED"):
            M._grid("idnode/delete")

    def test_channel_count_mismatch_blocks(self):
        self.channels["entries"].pop()
        self.channels["total"] = 1
        with self.assertRaisesRegex(M.PlanBlocked, "REFETCH_NOT_CONVERGED"):
            self.probe()


if __name__ == "__main__":
    unittest.main()
