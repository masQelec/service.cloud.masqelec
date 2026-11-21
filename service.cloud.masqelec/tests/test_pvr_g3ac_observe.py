"""G3-AC observer: synthetic identity tracking and safe failure gates."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3ac_observe.py"
spec = importlib.util.spec_from_file_location("pvr_g3ac_observe", path)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def tvh(a="G3AB Alpha", b="G3AB Beta", au="uuid-a", bu="uuid-b"):
    return [{"name": a, "uuid": au}, {"name": b, "uuid": bu}]

def kodi(a="G3AB Alpha", b="G3AB Beta", ai=3, bi=2):
    return [{"channelid": ai, "label": a}, {"channelid": bi, "label": b}]

class ObserveTests(unittest.TestCase):
    def test_first_sample_has_no_stability_claim(self):
        r = m.evaluate(tvh(), kodi())
        self.assertEqual(r["status"], "OBSERVED_ONLY")
        self.assertTrue(r["names_match"])
        self.assertIsNone(r["kodi_ids_stable_since_sample1"])

    def test_second_sample_stable_ids(self):
        base = m.identity_snapshot(tvh(), kodi())
        r = m.evaluate(tvh(), kodi(), base)
        self.assertTrue(r["kodi_ids_stable_since_sample1"])
        self.assertTrue(r["tvh_uuids_stable_since_sample1"])

    def test_old_kodi_ids_are_valid_dynamic_baseline(self):
        base = m.identity_snapshot(tvh(), kodi(ai=2, bi=1))
        r = m.evaluate(tvh(), kodi(ai=2, bi=1), base)
        self.assertTrue(r["kodi_ids_stable_since_sample1"])

    def test_kodi_id_change_detected(self):
        base = m.identity_snapshot(tvh(), kodi())
        r = m.evaluate(tvh(), kodi(ai=4), base)
        self.assertFalse(r["kodi_ids_stable_since_sample1"])

    def test_tvh_uuid_change_detected(self):
        base = m.identity_snapshot(tvh(), kodi())
        r = m.evaluate(tvh(au="new-uuid"), kodi(), base)
        self.assertFalse(r["tvh_uuids_stable_since_sample1"])

    def test_renamed_tvh_only_mismatch(self):
        r = m.evaluate(tvh(a="G3AB Alpha Renamed"), kodi())
        self.assertFalse(r["names_match"])

    def test_rename_both_matches_but_not_identity_stable_by_name(self):
        base = m.identity_snapshot(tvh(), kodi())
        r = m.evaluate(tvh(a="G3AB Alpha Renamed"),
                       kodi(a="G3AB Alpha Renamed"), base)
        self.assertTrue(r["names_match"])
        self.assertFalse(r["tvh_uuids_stable_since_sample1"])
        self.assertFalse(r["kodi_ids_stable_since_sample1"])

    def test_block_extra_channel(self):
        self.assertEqual(m.evaluate(tvh() + [{"name": "G3AB C", "uuid": "uuid-c"}],
                                    kodi())["status"], "BLOCKED_INVALID_INVENTORY")

    def test_block_unknown_source(self):
        self.assertEqual(m.evaluate(tvh(a="Production Channel"), kodi())["status"],
                         "BLOCKED_INVALID_INVENTORY")

    def test_block_duplicate_names(self):
        self.assertEqual(m.evaluate(tvh(a="G3AB Beta"), kodi())["status"],
                         "BLOCKED_INVALID_INVENTORY")

    def test_block_duplicate_uuid(self):
        self.assertEqual(m.evaluate(tvh(au="uuid-b"), kodi())["status"],
                         "BLOCKED_INVALID_INVENTORY")

    def test_block_duplicate_kodi_id(self):
        self.assertEqual(m.evaluate(tvh(), kodi(ai=2))["status"],
                         "BLOCKED_INVALID_INVENTORY")

    def test_no_cuid_mapping_claim(self):
        self.assertFalse(m.evaluate(tvh(), kodi())["cuid_mapping_proven"])

    def test_no_sqlite_claim(self):
        self.assertFalse(m.evaluate(tvh(), kodi())["sqlite_touched"])

    def test_not_claim_htsp_events(self):
        self.assertEqual(m.evaluate(tvh(), kodi())["htsp_event_seen"], "NOT_MEASURED")

    def test_run_fails_on_identity_churn(self):
        with patch.object(m, "get_tvh", side_effect=[tvh(), tvh(au="new")]), \
             patch.object(m, "get_kodi", side_effect=[kodi(), kodi()]), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.run(2, 0), 2)

    def test_run_passes_on_stable_pair(self):
        with patch.object(m, "get_tvh", side_effect=[tvh(), tvh()]), \
             patch.object(m, "get_kodi", side_effect=[kodi(), kodi()]), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.run(2, 0), 0)

if __name__ == "__main__":
    unittest.main()
