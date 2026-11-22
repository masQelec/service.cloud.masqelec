"""G3-AT: offline-only tests for positional M3U reorder in the private G3-AN generator."""
import importlib.util
from pathlib import Path
import unittest


PREPARE = Path(__file__).resolve().parents[1] / "lab/pvr_g3ab/g3an/prepare.py"
spec = importlib.util.spec_from_file_location("g3at_g3an_prepare", PREPARE)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def entries(m3u):
    lines = m3u.splitlines()
    assert lines[0] == "#EXTM3U"
    assert len(lines) == 5
    return [(lines[i], lines[i + 1]) for i in (1, 3)]


class G3ATReorderTests(unittest.TestCase):
    def test_live_baseline_unchanged(self):
        current = prepare.playlist("live")
        self.assertEqual([url for _, url in entries(current)],
                         ["http://g3ap-live:8080/ch1.ts", "http://streams/ch2.ts"])

    def test_reorder_only_changes_position(self):
        live_entries = entries(prepare.playlist("live"))
        reversed_entries = entries(prepare.playlist("reorder"))
        # Same complete metadata and URLs; only order changes.
        self.assertEqual(reversed_entries, list(reversed(live_entries)))
        for metadata, url in reversed_entries:
            self.assertIn('CUID="g3an-', metadata)
            self.assertTrue(url.startswith("http://"))

    def test_no_cuid_or_number_reassignment(self):
        for stage in ("live", "reorder"):
            mapping = {metadata.split('CUID="')[1].split('"')[0]: metadata
                       for metadata, _ in entries(prepare.playlist(stage))}
            self.assertEqual(set(mapping), {"g3an-001", "g3an-002"})
            self.assertIn('tvh-chnum="1"', mapping["g3an-001"])
            self.assertIn('tvh-chnum="2"', mapping["g3an-002"])


if __name__ == "__main__":
    unittest.main()
