"""G3-S read-only consecutive snapshot gate tests (no network/no sleeps)."""
import copy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, MagicMock

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3s_tvh_two_snapshots.py"
spec = importlib.util.spec_from_file_location("g3s", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)
M3U = b'#EXTM3U\n#EXTINF:-1 group-title="A",one\nurl1\n#EXTINF:-1 group-title="B",two\nurl2\n'


class TwoSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tags = [
            {"uuid": "a", "name": "A"}, {"uuid": "b", "name": "B"},
            {"uuid": "old", "name": "Old"},
        ]
        self.channels = [
            {"uuid": "c1", "tags": ["a"]}, {"uuid": "c2", "tags": ["b"]},
        ]

    def _capture(self, raw=M3U):
        calls = []
        def grid(endpoint):
            calls.append(endpoint)
            return copy.deepcopy(
                self.tags if endpoint == "channeltag/grid" else self.channels)
        fake_path = MagicMock()
        fake_path.is_file.return_value = True
        fake_path.is_symlink.return_value = False
        fake_path.open.return_value.__enter__.return_value.read.return_value = raw
        with patch.object(M, "M3U", fake_path), patch.object(M, "_grid", side_effect=grid):
            result = M.capture()
        self.assertEqual(calls, ["channeltag/grid", "channel/grid"])
        return result

    def test_stable_two_snapshots(self):
        result = self._capture()
        got = M.compare(result, copy.deepcopy(result))
        self.assertEqual(got["status"], "STABLE_TWO_SNAPSHOTS")
        self.assertEqual(got["tvh_channels"], 2)
        self.assertEqual(got["unmatched_historic_tags"], 1)

    def test_channel_membership_change_blocks(self):
        a = self._capture()
        self.channels[0]["tags"] = ["b"]
        b = self._capture()
        with self.assertRaisesRegex(M.GateBlocked, "TVH_CHANNEL_MEMBERSHIP_CHANGED"):
            M.compare(a, b)

    def test_channel_uuid_change_blocks(self):
        a = self._capture()
        self.channels[1]["uuid"] = "changed"
        b = self._capture()
        with self.assertRaisesRegex(M.GateBlocked, "TVH_CHANNEL_MEMBERSHIP_CHANGED"):
            M.compare(a, b)

    def test_tag_uuid_change_blocks(self):
        a = self._capture()
        self.tags[1]["uuid"] = "other"
        self.channels[1]["tags"] = ["other"]
        b = self._capture()
        with self.assertRaisesRegex(M.GateBlocked, "TVH_TAG_INVENTORY_CHANGED"):
            M.compare(a, b)

    def test_modified_playlist_blocks(self):
        a = self._capture()
        b = self._capture(M3U + b"\n")
        with self.assertRaisesRegex(M.GateBlocked, "PLAYLIST_CHANGED_BETWEEN_SNAPSHOTS"):
            M.compare(a, b)

    def test_missing_group_blocks(self):
        self.tags.pop(1)
        with self.assertRaisesRegex(M.GateBlocked, "M3U_GROUP_NOT_IN_TVH"):
            self._capture()

    def test_untagged_channel_blocks(self):
        self.channels[0]["tags"] = []
        with self.assertRaisesRegex(M.GateBlocked, "TVH_CHANNEL_LINK_INVALID"):
            self._capture()

    def test_channel_count_mismatch_blocks(self):
        self.channels.pop()
        with self.assertRaisesRegex(M.GateBlocked, "TVH_CHANNEL_COUNT_MISMATCH"):
            self._capture()

    def test_group_has_no_channel_links_blocks(self):
        self.channels[1]["tags"] = ["a"]
        a = self._capture()
        with self.assertRaisesRegex(M.GateBlocked, "M3U_GROUP_WITHOUT_CHANNEL_LINKS"):
            M.compare(a, a)

    def test_invalid_interval_blocks_before_capture(self):
        with self.assertRaisesRegex(M.GateBlocked, "INVALID_DELAY"):
            M.run(delay=30, read=lambda: self.fail("capture called"))

    def test_two_capture_run_uses_injected_sleep(self):
        a = self._capture()
        times = []
        got = M.run(delay=75, read=lambda: copy.deepcopy(a), sleep=times.append)
        self.assertEqual(times, [75])
        self.assertEqual(got["status"], "STABLE_TWO_SNAPSHOTS")

    def test_write_endpoints_unavailable(self):
        with self.assertRaisesRegex(M.GateBlocked, "ENDPOINT_NOT_ALLOWED"):
            M._grid("idnode/delete")


if __name__ == "__main__":
    unittest.main()
