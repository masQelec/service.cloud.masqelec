"""G3-Y privacy-preserving field inventory tests, no live network."""
import importlib.util
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3y_identity_fields_lab.py"
spec = importlib.util.spec_from_file_location("pvr_g3y_identity_fields_lab", source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class IdentityFieldTests(unittest.TestCase):
    def test_fields_never_establish_cross_system_mapping(self):
        r = m._summary([{"uuid": "u1", "name": "One", "services": []}],
                       [{"channelid": 1, "label": "One"}])
        self.assertEqual(r["cuid_to_tvh_uuid_proven"], "NO")
        self.assertEqual(r["tvh_uuid_to_kodi_channelid_proven"], "NO")
        self.assertEqual(r["identity_deletion_authorized"], "NO")

    def test_no_names_or_urls_in_output(self):
        r = m._summary([{"uuid": "u", "name": "Secret Name", "url": "secret.url"}],
                       [{"channelid": 1, "label": "Secret Name"}])
        text = str(r)
        self.assertNotIn("Secret Name", text)
        self.assertNotIn("secret.url", text)

    def test_absent_id_is_visible(self):
        r = m._summary([{"name": "A"}], [{"label": "A"}])
        self.assertNotIn("uuid", r["tvh_fields_present_all"])
        self.assertNotIn("channelid", r["kodi_fields_present_all"])

    def test_partial_tvh_denied(self):
        with self.assertRaises(m.Blocked):
            m._rows({"entries": [{"uuid": "a"}], "total": 2}, "entries")

    def test_partial_kodi_denied(self):
        with self.assertRaises(m.Blocked):
            m._rows({"channels": [{"channelid": 1}], "limits": {"total": 2}}, "channels")

    def test_empty_denied(self):
        with self.assertRaises(m.Blocked):
            m._rows({"entries": [], "total": 0}, "entries")

    def test_invalid_total_bool_denied(self):
        with self.assertRaises(m.Blocked):
            m._rows({"entries": [{"uuid":"a"}], "total": True}, "entries")

    def test_invalid_row_denied(self):
        with self.assertRaises(m.Blocked):
            m._rows({"entries": ["oops"], "total": 1}, "entries")

    def test_summary_no_sqlite(self):
        r = m._summary([{"uuid": "x"}], [{"channelid": 1}])
        self.assertEqual(r["sqlite_touched"], "NO")

    def test_non_lab_endpoints_denied(self):
        with self.assertRaises(m.Blocked):
            m.probe("http://127.0.0.1:9981", "http://127.0.0.1:8080")

    def test_type_inspection_without_values(self):
        r = m._summary([{"uuid": "one", "services": [1]}],
                       [{"channelid": 1}])
        self.assertEqual(r["tvh_identity_field_types"]["services"], ["list"])
        self.assertEqual(r["kodi_identity_field_types"]["channelid"], ["int"])

    def test_common_field_intersection(self):
        r = m._summary([{"uuid": "1", "name": "A"}, {"uuid": "2"}],
                       [{"channelid": 1, "label": "A"}, {"channelid": 2}])
        self.assertEqual(r["tvh_fields_present_all"], ["uuid"])
        self.assertEqual(r["kodi_fields_present_all"], ["channelid"])


if __name__ == "__main__":
    unittest.main()
