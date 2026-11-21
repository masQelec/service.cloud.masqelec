"""Unit tests for G3-AC observation gate."""
import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3ac_observe.py"
spec = importlib.util.spec_from_file_location("pvr_g3ac_observe", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def tvh(a="G3AB Alpha", b="G3AB Beta"):
    return [{"name": a}, {"name": b}]

def kodi(a="G3AB Alpha", b="G3AB Beta"):
    return [{"channelid": 2, "label": a}, {"channelid": 1, "label": b}]

class ObserveTests(unittest.TestCase):
    def test_match(self):
        r = m.evaluate(tvh(), kodi())
        self.assertEqual(r["status"], "OBSERVED_ONLY")
        self.assertTrue(r["names_match"])
        self.assertTrue(r["id_preserved"])

    def test_stale_label(self):
        r = m.evaluate(tvh("G3AB Alpha Renamed"), kodi())
        self.assertFalse(r["names_match"])
        self.assertTrue(r["id_preserved"])

    def test_converged_label(self):
        r = m.evaluate(tvh("G3AB Alpha Renamed"), kodi("G3AB Alpha Renamed"))
        self.assertTrue(r["names_match"])

    def test_block_extra_channel(self):
        self.assertEqual(m.evaluate(tvh() + [{"name":"G3AB C"}], kodi())["status"],
                         "BLOCKED_INVENTORY_NOT_TWO")

    def test_block_unexpected_source(self):
        self.assertEqual(m.evaluate(tvh("Other"), kodi())["status"],
                         "BLOCKED_UNEXPECTED_SOURCE")

    def test_no_cuid_claim(self):
        self.assertFalse(m.evaluate(tvh(), kodi())["cuid_mapping_proven"])

    def test_no_sqlite(self):
        self.assertFalse(m.evaluate(tvh(), kodi())["sqlite_touched"])

    def test_not_claim_htsp_events(self):
        self.assertEqual(m.evaluate(tvh(), kodi())["htsp_event_seen"], "NOT_MEASURED")

    def test_id_change_recorded(self):
        self.assertFalse(m.evaluate(tvh(), [{"channelid": 6, "label": "G3AB Alpha"},
                                           {"channelid": 1, "label": "G3AB Beta"}])["id_preserved"])

if __name__ == "__main__":
    unittest.main()
