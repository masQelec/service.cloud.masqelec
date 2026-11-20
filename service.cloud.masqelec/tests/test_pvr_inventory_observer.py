"""G2 regression tests; pure functions, no Kodi/TVH IO."""
import importlib.util
from pathlib import Path
import sys
import unittest

FILE = Path(__file__).resolve().parents[1] / "lib" / "pvr_inventory_observer.py"
spec = importlib.util.spec_from_file_location("pvr_inventory_observer", FILE)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class InventoryObserverTests(unittest.TestCase):
    def setUp(self):
        self.tvh = [mod.TVHChannel("uuid-A", 1, ("TDT",)),
                    mod.TVHChannel("uuid-B", 2, ("CINE",))]
        self.kodi = [mod.KodiChannel(1, 501, 1, ("TDT",)),
                     mod.KodiChannel(1, 502, 2, ("CINE",))]
        self.crosswalk = {"uuid-A": (1, 501), "uuid-B": (1, 502)}

    def test_equal_verified(self):
        result = mod.compare_inventories(self.tvh, self.kodi, self.crosswalk)
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertFalse(result["destructive_operations_authorized"])

    def test_without_crosswalk_no_deletion(self):
        result = mod.compare_inventories(self.tvh, self.kodi)
        self.assertEqual(result["status"], "BLOCKED_UNVERIFIED_CROSSWALK")
        self.assertEqual(result["orphan_candidates"], [])

    def test_partial_crosswalk_blocks(self):
        result = mod.compare_inventories(self.tvh, self.kodi, {"uuid-A": (1, 501)})
        self.assertEqual(result["status"], "BLOCKED_INCOMPLETE_CROSSWALK")

    def test_identify_one_orphan_by_verified_identity(self):
        kodi = self.kodi + [mod.KodiChannel(1, 999, 3, ("CINE",))]
        result = mod.compare_inventories(self.tvh, kodi, self.crosswalk)
        self.assertEqual(result["status"], "DIFFERENT")
        self.assertEqual(result["orphan_candidates"], [(1, 999)])
        self.assertFalse(result["destructive_operations_authorized"])

    def test_missing_channel_and_number_and_group(self):
        kodi = [mod.KodiChannel(1, 501, 99, ("MUSIC",))]
        result = mod.compare_inventories(self.tvh, kodi, self.crosswalk)
        self.assertEqual(result["missing_candidates"], ["uuid-B"])
        self.assertEqual(result["number_mismatches"], ["uuid-A"])
        self.assertEqual(result["group_mismatches"], ["uuid-A"])

    def test_duplicate_name_not_used(self):
        # Deliberately no name field; UUID and client unique ID only.
        self.assertEqual(mod.compare_inventories(self.tvh, self.kodi, self.crosswalk)["status"], "UNCHANGED")

    def test_duplicate_tvh_uuid_rejected(self):
        with self.assertRaises(mod.InventoryError):
            mod.compare_inventories(self.tvh + self.tvh[:1], self.kodi, self.crosswalk)

    def test_duplicate_kodi_key_rejected(self):
        with self.assertRaises(mod.InventoryError):
            mod.compare_inventories(self.tvh, self.kodi + self.kodi[:1], self.crosswalk)

    def test_non_unique_crosswalk_blocks(self):
        result = mod.compare_inventories(
            self.tvh, self.kodi, {"uuid-A": (1, 501), "uuid-B": (1, 501)}
        )
        self.assertEqual(result["status"], "BLOCKED_INCOMPLETE_CROSSWALK")


if __name__ == "__main__":
    unittest.main()
