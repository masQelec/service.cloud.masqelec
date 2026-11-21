"""G3-Z tests: TVH service shapes, no ID/URL leakage or mutation."""
import importlib.util
from pathlib import Path
import unittest

source = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3z_tvh_service_shapes_lab.py"
spec = importlib.util.spec_from_file_location("pvr_g3z_tvh_service_shapes_lab", source)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class ServiceShapesTests(unittest.TestCase):
    def test_string_reference(self):
        r = m.inspect({"total": 1, "entries": [{"uuid": "a", "services": ["private-service"]}]})
        self.assertEqual(r["reference_shapes"], {"str": 1})
        self.assertNotIn("private-service", str(r))

    def test_dict_reference_shows_keys_only(self):
        r = m.inspect({"total": 1, "entries": [{"uuid": "a", "services": [
            {"uuid": "private", "name": "secret"}]}]})
        self.assertEqual(r["reference_shapes"]["object_fields:name,uuid"], 1)
        self.assertNotIn("private", str(r))
        self.assertNotIn("secret", str(r))

    def test_empty_services_counts(self):
        r = m.inspect({"total": 2, "entries": [
            {"uuid": "a", "services": []},
            {"uuid": "b", "services": ["id"]}]})
        self.assertEqual((r["channels_with_no_services"], r["service_references"]), (1, 1))

    def test_empty_inventory_blocks(self):
        with self.assertRaises(m.Blocked):
            m.inspect({"total": 0, "entries": []})

    def test_partial_inventory_blocks(self):
        with self.assertRaises(m.Blocked):
            m.inspect({"total": 2, "entries": [{"uuid": "x", "services": []}]})

    def test_missing_uuid_blocks(self):
        with self.assertRaises(m.Blocked):
            m.inspect({"total": 1, "entries": [{"services": []}]})

    def test_missing_services_blocks(self):
        with self.assertRaises(m.Blocked):
            m.inspect({"total": 1, "entries": [{"uuid": "x"}]})

    def test_scalar_service_field_blocks(self):
        with self.assertRaises(m.Blocked):
            m.inspect({"total": 1, "entries": [{"uuid": "x", "services": "secret"}]})

    def test_unsafe_key_blocks(self):
        with self.assertRaises(m.Blocked):
            m.inspect({"total": 1, "entries": [{"uuid": "x", "services": [{"http://secret": 1}]}]})

    def test_no_cross_system_proof(self):
        r = m.inspect({"total": 1, "entries": [{"uuid": "x", "services": [1]}]})
        self.assertEqual(r["cuid_mapping_proven"], "NO")
        self.assertEqual(r["tvh_to_kodi_identity_proven"], "NO")
        self.assertEqual(r["deletion_authorized"], "NO")
        self.assertEqual(r["master_touched"], "NO")


if __name__ == "__main__":
    unittest.main()
