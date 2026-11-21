"""G3-AD deterministic unit checks; no live network access."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3ad_rename_watch.py"
spec = importlib.util.spec_from_file_location("pvr_g3ad_rename_watch", path)
import sys
sys.path.insert(0, str(path.parent))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def tvh(a="G3AB Alpha", au="uuid-a", bu="uuid-b"):
    return [{"name": a, "uuid": au}, {"name": "G3AB Beta", "uuid": bu}]

def kodi(a="G3AB Alpha", ai=3, bi=2):
    return [{"label": a, "channelid": ai}, {"label": "G3AB Beta", "channelid": bi}]

class RenameWatchTests(unittest.TestCase):
    def test_baseline(self):
        s = m.read_state(tvh(), kodi())
        self.assertIsNone(s["kodi_id_stable"])
        self.assertTrue(s["names_match"])

    def test_tvh_rename_without_kodi(self):
        base = m.read_state(tvh(), kodi())
        s = m.read_state(tvh(a=m.RENAMED), kodi(), base)
        self.assertTrue(s["tvh_alpha_renamed"])
        self.assertFalse(s["kodi_alpha_renamed"])
        self.assertTrue(s["tvh_uuid_stable"])
        self.assertTrue(s["kodi_id_stable"])

    def test_kodi_converges(self):
        base = m.read_state(tvh(), kodi())
        s = m.read_state(tvh(a=m.RENAMED), kodi(a=m.RENAMED), base)
        self.assertTrue(s["names_match"])
        self.assertTrue(s["kodi_alpha_renamed"])

    def test_tvh_alpha_uuid_changed(self):
        base = m.read_state(tvh(), kodi())
        self.assertFalse(m.read_state(tvh(au="new"), kodi(), base)["tvh_uuid_stable"])

    def test_tvh_beta_uuid_changed(self):
        base = m.read_state(tvh(), kodi())
        self.assertFalse(m.read_state(tvh(bu="new"), kodi(), base)["tvh_uuid_stable"])

    def test_kodi_alpha_id_changed(self):
        base = m.read_state(tvh(), kodi())
        self.assertFalse(m.read_state(tvh(), kodi(ai=9), base)["kodi_id_stable"])

    def test_kodi_beta_id_changed(self):
        base = m.read_state(tvh(), kodi())
        self.assertFalse(m.read_state(tvh(), kodi(bi=9), base)["kodi_id_stable"])

    def test_reject_pre_renamed_baseline(self):
        with self.assertRaisesRegex(ValueError, "RENAME_ALREADY"):
            m.read_state(tvh(a=m.RENAMED), kodi())

    def test_reject_duplicate_name(self):
        rows = tvh()
        rows[1]["name"] = rows[0]["name"]
        with self.assertRaises(ValueError):
            m.read_state(rows, kodi())

    def test_reject_unexpected_source(self):
        with self.assertRaises(ValueError):
            m.read_state(tvh(a="Real Channel"), kodi())

    def test_reject_absent_pvr_channels(self):
        with self.assertRaises(ValueError):
            m.read_state(tvh(), [])

    def test_reject_duplicate_kodi_id(self):
        with self.assertRaises(ValueError):
            m.read_state(tvh(), kodi(bi=3))

    def test_reject_duplicate_tvh_uuid(self):
        with self.assertRaises(ValueError):
            m.read_state(tvh(bu="uuid-a"), kodi())

    def test_read_only_run_tvh_rename_without_kodi(self):
        with patch.object(m.data, "get_tvh", side_effect=[tvh(), tvh(a=m.RENAMED)]), \
             patch.object(m.data, "get_kodi", side_effect=[kodi(), kodi()]), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.run(2, 1), 4)

    def test_read_only_run_both_rename(self):
        with patch.object(m.data, "get_tvh", side_effect=[tvh(), tvh(a=m.RENAMED)]), \
             patch.object(m.data, "get_kodi", side_effect=[kodi(), kodi(a=m.RENAMED)]), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.run(2, 1), 0)

    def test_read_only_run_no_rename(self):
        with patch.object(m.data, "get_tvh", side_effect=[tvh(), tvh()]), \
             patch.object(m.data, "get_kodi", side_effect=[kodi(), kodi()]), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.run(2, 1), 3)

    def test_read_only_run_id_churn_stops(self):
        with patch.object(m.data, "get_tvh", side_effect=[tvh(), tvh()]), \
             patch.object(m.data, "get_kodi", side_effect=[kodi(), kodi(ai=4)]), \
             patch.object(m.time, "sleep"):
            self.assertEqual(m.run(2, 1), 2)

if __name__ == "__main__":
    unittest.main()
