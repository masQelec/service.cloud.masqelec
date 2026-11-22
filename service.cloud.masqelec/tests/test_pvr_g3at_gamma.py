"""G3-AT-P2C offline checks: no runtime mutations or Docker calls."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
PREPARE = ROOT / "lab/pvr_g3ab/g3an/prepare.py"
SERVER = ROOT / "lab/pvr_g3ab/g3ap/server.py"

spec = importlib.util.spec_from_file_location("g3at_prepare_gamma", PREPARE)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def entries(stage):
    lines = prepare.playlist(stage).splitlines()
    if lines[0] != "#EXTM3U" or len(lines[1:]) % 2:
        raise AssertionError("INVALID_M3U_STRUCTURE")
    return [(lines[i], lines[i + 1]) for i in range(1, len(lines), 2)]


class GammaOfflineTests(unittest.TestCase):
    def test_existing_reorder_entries_unchanged(self):
        self.assertEqual(entries("add-gamma")[:2], entries("reorder"))

    def test_gamma_identity_and_source_are_unique(self):
        gamma = entries("add-gamma")
        self.assertEqual(len(gamma), 3)
        self.assertEqual({m.split('CUID="')[1].split('"')[0] for m, _ in gamma},
                         {"g3an-001", "g3an-002", "g3an-003"})
        self.assertEqual(len({url for _, url in gamma}), 3)
        self.assertIn('tvh-chnum="3"', gamma[2][0])
        self.assertIn('tvg-chno="3"', gamma[2][0])
        self.assertEqual(gamma[2][1], "http://g3ap-live:8080/ch3.ts")

    def test_gamma_route_uses_existing_read_only_fixture(self):
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('"/ch3.ts": SOURCE / "ch1.ts"', source)
        self.assertNotIn('SOURCE / "ch3.ts"', source)

    def test_legacy_stages_not_extended(self):
        self.assertEqual(len(entries("live")), 2)
        self.assertEqual(len(entries("reorder")), 2)
        self.assertEqual(len(entries("baseline")), 2)


if __name__ == "__main__":
    unittest.main()
