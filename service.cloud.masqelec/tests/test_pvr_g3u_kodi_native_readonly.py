"""Kodi PVR native read-only diagnostics; no live services."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

file = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3u_kodi_native_readonly.py"
spec = importlib.util.spec_from_file_location("pvr_g3u_native", file)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)


class KodiNativeTests(unittest.TestCase):
    def test_exact_equal(self):
        result = M.summarize([{"name": "A"}, {"name": "B"}],
                             [{"label": "A"}, {"label": "B"}])
        self.assertEqual(result["status"], "DESCRIPTIVE_MATCH")
        self.assertEqual(result["kodi_unmatched_names"], 0)

    def test_orphan_in_kodi(self):
        got = M.summarize([{"name": "A"}],
                          [{"label": "A"}, {"label": "Old"}])
        self.assertEqual(got["status"], "DESCRIPTIVE_MISMATCH")
        self.assertEqual(got["kodi_unmatched_names"], 1)

    def test_channel_missing_in_kodi(self):
        got = M.summarize([{"name": "A"}, {"name": "New"}],
                          [{"label": "A"}])
        self.assertEqual(got["tvh_missing_in_kodi_names"], 1)

    def test_duplicate_names_counted_not_dropped(self):
        got = M.summarize([{"name": "A"}, {"name": "A"}],
                          [{"label": "A"}])
        self.assertEqual(got["tvh_missing_in_kodi_names"], 1)
        self.assertEqual(got["ambiguous_tvh_names"], 2)

    def test_ambiguous_same_count_does_not_prove_identity(self):
        got = M.summarize([{"name": "A"}, {"name": "A"}],
                          [{"label": "A"}, {"label": "A"}])
        self.assertEqual(got["status"], "DESCRIPTIVE_MATCH")
        self.assertEqual(got["cuid_mapping_proven"], "NO")

    def test_unavailable_name_fails_closed(self):
        with self.assertRaisesRegex(M.Blocked, "CHANNEL_NAME_UNAVAILABLE"):
            M.summarize([{"name": "A"}], [{"label": ""}])

    def test_only_alltv_group_is_queried(self):
        calls = []
        def fake(method, params):
            calls.append((method, params))
            if method == "PVR.GetChannelGroups":
                return {"channelgroups": [
                    {"channelgroupid": "alltv", "label": "All channels"},
                    {"channelgroupid": 15, "label": "Other"},
                ]}
            return {"channels": [{"label": "A"}],
                    "limits": {"start": 0, "end": 1, "total": 1}}
        with patch.object(M, "kodi", side_effect=fake):
            self.assertEqual(len(M.kodi_all_tv()), 1)
        self.assertEqual(calls[1][1]["channelgroupid"], "alltv")

    def test_no_alltv_blocks(self):
        with patch.object(M, "kodi", return_value={"channelgroups": []}):
            with self.assertRaisesRegex(M.Blocked, "KODI_ALLTV_NOT_UNAMBIGUOUS"):
                M.kodi_all_tv()

    def test_partial_jsonrpc_channels_blocks(self):
        def fake(method, params):
            if method == "PVR.GetChannelGroups":
                return {"channelgroups": [{"channelgroupid": "alltv"}]}
            return {"channels": [{"label": "A"}],
                    "limits": {"total": 2}}
        with patch.object(M, "kodi", side_effect=fake):
            with self.assertRaisesRegex(M.Blocked, "KODI_CHANNELS_PARTIAL"):
                M.kodi_all_tv()

    def test_restricted_methods(self):
        with self.assertRaisesRegex(M.Blocked, "UNSUPPORTED_KODI_METHOD"):
            M.kodi("VideoLibrary.Clean", {})


if __name__ == "__main__":
    unittest.main()
