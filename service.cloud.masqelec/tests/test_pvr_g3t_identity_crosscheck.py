"""G3-T read-only descriptive M3U/TVH link checks; no network access."""
import importlib.util
from pathlib import Path
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3t_identity_crosscheck.py"
spec = importlib.util.spec_from_file_location("g3t", SCRIPT)
M = importlib.util.module_from_spec(spec)
spec.loader.exec_module(M)

PLAYLIST = ('#EXTM3U\n'
            '#EXTINF:-1 group-title="A",One\nhttp://example.invalid/1\n'
            '#EXTINF:-1 group-title="B",Two\nhttp://example.invalid/2\n')
TAGS = [{"uuid": "tag-a", "name": "A"}, {"uuid": "tag-b", "name": "B"},
        {"uuid": "historic", "name": "Old"}]
CHANNELS = [{"uuid": "c1", "name": "One", "tags": ["tag-a"]},
            {"uuid": "c2", "name": "Two", "tags": ["tag-b"]}]


class IdentityTests(unittest.TestCase):
    def test_exact_match(self):
        outcome = M.compare(M.parse_m3u(PLAYLIST), TAGS, CHANNELS)
        self.assertEqual(outcome["match_gate"], "PASS")
        self.assertEqual(outcome["exact_name_group_matches"], 2)
        self.assertEqual(outcome["cuid_mapping_proven"], "NO")

    def test_missing_link_fails(self):
        channels = [dict(CHANNELS[0]), dict(CHANNELS[1])]
        channels[1]["tags"] = ["tag-a"]
        got = M.compare(M.parse_m3u(PLAYLIST), TAGS, channels)
        self.assertEqual(got["match_gate"], "INCOMPLETE")
        self.assertEqual(got["missing_name_group_pairs"], 1)

    def test_mismatched_name_fails(self):
        channels = [dict(CHANNELS[0]), dict(CHANNELS[1])]
        channels[1]["name"] = "Different"
        self.assertEqual(M.compare(M.parse_m3u(PLAYLIST), TAGS, channels)["match_gate"],
                         "INCOMPLETE")

    def test_legacy_extra_group_does_not_block(self):
        tags = TAGS
        channels = [dict(CHANNELS[0]), dict(CHANNELS[1])]
        channels[1]["tags"] = ["tag-b", "historic"]
        result = M.compare(M.parse_m3u(PLAYLIST), tags, channels)
        self.assertEqual(result["match_gate"], "PASS")
        self.assertEqual(result["tvh_multitag_channels"], 1)

    def test_duplicate_descriptive_pair_is_ambiguous(self):
        m3u = M.parse_m3u(PLAYLIST +
                          '#EXTINF:-1 group-title="A",One\nhttp://example.invalid/3\n')
        channels = CHANNELS + [{"uuid": "c3", "name": "One", "tags": ["tag-a"]}]
        got = M.compare(m3u, TAGS, channels)
        self.assertEqual(got["m3u_ambiguous_duplicate_entries"], 2)
        self.assertEqual(got["match_gate"], "PASS")
        self.assertEqual(got["identity_disambiguation"], "NOT_PROVEN")
        self.assertEqual(got["cuid_mapping_proven"], "NO")

    def test_missing_group_in_m3u_blocks(self):
        with self.assertRaisesRegex(M.Blocked, "INVALID_EXTINF"):
            M.parse_m3u('#EXTM3U\n#EXTINF:-1,One\nhttp://example.invalid/1')

    def test_unknown_tag_reference_blocks(self):
        channels = [{"uuid": "c1", "name": "One", "tags": ["absent"]}]
        with self.assertRaisesRegex(M.Blocked, "UNKNOWN_TAG_REFERENCE"):
            M.compare(M.parse_m3u(PLAYLIST), TAGS, channels)

    def test_duplicate_channel_uuid_blocks(self):
        channels = CHANNELS + [dict(CHANNELS[0])]
        with self.assertRaisesRegex(M.Blocked, "INVALID_CHANNEL_UUID"):
            M.compare(M.parse_m3u(PLAYLIST), TAGS, channels)

    def test_nfc_names_match(self):
        m3u = M.parse_m3u('#EXTM3U\n#EXTINF:-1 group-title="Café",Niño\nu\n')
        tags = [{"uuid": "g", "name": "Cafe\u0301"}]
        channels = [{"uuid": "c", "name": "Nin\u0303o", "tags": ["g"]}]
        self.assertEqual(M.compare(m3u, tags, channels)["match_gate"], "PASS")

    def test_unapproved_endpoint(self):
        with self.assertRaisesRegex(M.Blocked, "UNAPPROVED_ENDPOINT"):
            M._grid("idnode/delete")


if __name__ == "__main__":
    unittest.main()
