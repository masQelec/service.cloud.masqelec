"""G3-P read-only shadow audit tests; no live TVH/Kodi calls."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.pvr_tag_shadow import audit

PLAYLIST = '#EXTM3U\n#EXTINF:-1 group-title="A",one\nurl1\n#EXTINF:-1 group-title="B",two\nurl2\n'


class G3PShadowTests(unittest.TestCase):
    def setUp(self):
        self.tags = {"total": 3, "entries": [
            {"uuid": "a", "name": "A", "internal": False},
            {"uuid": "b", "name": "B", "internal": False},
            {"uuid": "old", "name": "Old", "internal": False},
        ]}
        self.channels = {"total": 2, "entries": [
            {"uuid": "c1", "tags": ["a"]},
            {"uuid": "c2", "tags": ["b"]},
        ]}
        self.calls = []

    def api(self, endpoint, query):
        self.calls.append(endpoint)
        data = self.tags if endpoint == "channeltag/grid" else self.channels
        return True, 200, data.copy(), ""

    def inspect(self, read_text=lambda _: PLAYLIST):
        return audit("/not/touched/playlist.m3u", self.api, read_text)

    def test_success_and_no_writes(self):
        result = self.inspect()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["unowned_empty_count"], 1)
        self.assertEqual(result["create_count"], 0)
        self.assertFalse(result["write_executed"])
        self.assertEqual(self.calls,
                         ["channeltag/grid", "channel/grid"] * 2)

    def test_block_on_partial_grid(self):
        self.tags["total"] = 4
        self.assertEqual(self.inspect()["status"], "BLOCKED")

    def test_block_on_m3u_count_change(self):
        self.channels["total"] = 1
        self.channels["entries"].pop()
        self.assertEqual(self.inspect()["status"], "BLOCKED")

    def test_block_on_drift(self):
        n = [0]
        def getter(endpoint, query):
            n[0] += 1
            if n[0] == 3:
                self.tags = {"total": 2, "entries": self.tags["entries"][:2]}
            return True, 200, (self.tags if endpoint == "channeltag/grid"
                               else self.channels), ""
        result = audit("x", getter, lambda _: PLAYLIST)
        self.assertEqual(result["status"], "BLOCKED")

    def test_invalid_playlist_blocks(self):
        self.assertEqual(self.inspect(lambda _: "invalid")["status"], "BLOCKED")

    def test_auth_failure_blocks(self):
        result = audit("x", lambda e, query: (False, 401, None, ""), lambda _: PLAYLIST)
        self.assertEqual(result["status"], "BLOCKED")

    def test_no_write_symbols_in_module(self):
        import inspect
        import lib.pvr_tag_shadow as target
        source = inspect.getsource(target)
        self.assertNotIn("idnode/delete", source)
        self.assertNotIn("channeltag/create", source)


if __name__ == "__main__":
    unittest.main()
