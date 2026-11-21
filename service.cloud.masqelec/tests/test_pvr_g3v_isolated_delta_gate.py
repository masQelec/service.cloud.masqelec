"""G3-V lab acceptance: synthetic fixtures only."""
import copy
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3v_isolated_delta_gate.py"
spec = importlib.util.spec_from_file_location("g3v_delta", SOURCE)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


def report():
    def stage(tvh, kodi):
        return {"tvh": copy.deepcopy(tvh), "kodi": copy.deepcopy(kodi), "tvh_refetch_observed": True}
    t0 = [{"id": "tvh-1", "name": "One"}, {"id": "tvh-2", "name": "Two"}]
    k0 = [{"id": "kodi-1", "name": "One"}, {"id": "kodi-2", "name": "Two"}]
    t1 = t0 + [{"id": "tvh-3", "name": "Three"}]
    k1 = k0 + [{"id": "kodi-3", "name": "Three"}]
    return {
        "schema": 1, "lab_isolated": True,
        "kodi_connected_only_to_lab_tvh": True,
        "production_untouched": True,
        "stages": {"before": stage(t0, k0),
                   "added": stage(t1, k1),
                   "removed": stage(t0, k0)}
    }


class LabDeltaTests(unittest.TestCase):
    def test_add_remove_roundtrip_passes(self):
        self.assertEqual(M.evaluate(report())["lab_delta"], "PASS")

    def test_requires_isolation(self):
        data = report()
        data["lab_isolated"] = False
        with self.assertRaisesRegex(M.GateBlocked, "ISOLATION_NOT_PROVEN"):
            M.evaluate(data)

    def test_requires_lab_kodi_connection(self):
        data = report()
        data["kodi_connected_only_to_lab_tvh"] = False
        with self.assertRaisesRegex(M.GateBlocked, "KODI_LAB_CONNECTION_NOT_PROVEN"):
            M.evaluate(data)

    def test_requires_refetch_event(self):
        data = report()
        data["stages"]["added"]["tvh_refetch_observed"] = False
        with self.assertRaisesRegex(M.GateBlocked, "TVH_REFETCH_NOT_OBSERVED"):
            M.evaluate(data)

    def test_kodi_retains_orphan_blocks(self):
        data = report()
        data["stages"]["removed"]["kodi"] = data["stages"]["added"]["kodi"]
        with self.assertRaisesRegex(M.GateBlocked, "EXPECTED_DELTA_NOT_OBSERVED"):
            M.evaluate(data)

    def test_unchanged_tvh_identity_changed_blocks(self):
        data = report()
        data["stages"]["removed"]["tvh"][0]["id"] = "recreated"
        with self.assertRaisesRegex(M.GateBlocked, "TVH_DELTA_NOT_CONVERGED"):
            M.evaluate(data)

    def test_unchanged_kodi_identity_changed_blocks(self):
        data = report()
        data["stages"]["removed"]["kodi"][0]["id"] = "recreated"
        with self.assertRaisesRegex(M.GateBlocked, "KODI_DELTA_NOT_CONVERGED"):
            M.evaluate(data)

    def test_channel_renaming_blocks_even_with_stable_ids(self):
        data = report()
        data["stages"]["added"]["tvh"][0]["name"] = "Changed"
        with self.assertRaisesRegex(M.GateBlocked, "TVH_RETAINED_CHANNEL_CHANGED"):
            M.evaluate(data)

    def test_duplicate_ids_block(self):
        data = report()
        data["stages"]["added"]["tvh"][2]["id"] = "tvh-1"
        with self.assertRaisesRegex(M.GateBlocked, "INVALID_TVH_IDENTITY"):
            M.evaluate(data)

    def test_missing_production_fence_blocks(self):
        data = report()
        data.pop("production_untouched")
        with self.assertRaisesRegex(M.GateBlocked, "PRODUCTION_UNTOUCHED_NOT_PROVEN"):
            M.evaluate(data)


if __name__ == "__main__":
    unittest.main()
