"""G3-E read-only channel-to-group audit fixtures."""
import importlib.util
from pathlib import Path
import sys
import unittest

PATH = Path(__file__).resolve().parents[1] / "lib" / "pvr_group_audit.py"
SPEC = importlib.util.spec_from_file_location("pvr_group_audit", PATH)
MOD = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MOD
SPEC.loader.exec_module(MOD)
audit = MOD.audit
audit_with_numbers = MOD.audit_with_numbers

M3U = ('#EXTM3U\n'
       '#EXTINF:-1 group-title="B",Channel 1\nhttp://example.invalid/1\n'
       '#EXTINF:-1 group-title="A",Channel 2\nhttp://example.invalid/2\n')


class GroupAuditTests(unittest.TestCase):
    def setUp(self):
        self.tags = {"total": 2, "entries": [
            {"uuid": "u1", "name": "A"},
            {"uuid": "u2", "name": "B"},
        ]}
        self.channels = {"total": 2, "entries": [
            {"uuid": "c1", "name": "Channel 1", "tags": ["u2"]},
            {"uuid": "c2", "name": "Channel 2", "tags": ["u1"]},
        ]}

    def run_audit(self, text=M3U):
        return audit(text, self.tags, self.channels)

    def test_matching_groups_never_authorizes_changes(self):
        result = self.run_audit()
        self.assertEqual(result["status"], "DIAGNOSTIC_ONLY")
        self.assertEqual(result["exact_unique_name_pairs"], 2)
        self.assertEqual(result["group_mismatch_count"], 0)
        self.assertFalse(result["apply_authorized"])

    def test_wrong_group_reported(self):
        self.channels["entries"][0]["tags"] = ["u1"]
        result = self.run_audit()
        self.assertEqual(result["group_mismatch_count"], 1)
        self.assertEqual(result["group_mismatch_samples"][0]["expected"], "B")
        self.assertFalse(result["apply_authorized"])

    def test_same_count_different_names_is_inconclusive(self):
        self.channels["entries"][0]["name"] = "Renamed"
        result = self.run_audit()
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["unresolved_m3u_channels"], 1)

    def test_duplicate_names_block_exact_identity(self):
        self.channels["entries"][1]["name"] = "Channel 1"
        result = self.run_audit()
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["duplicate_names_in_tvh"], 1)
        self.assertEqual(result["exact_unique_name_pairs"], 0)

    def test_duplicate_m3u_names_are_inconclusive(self):
        text = M3U.replace("Channel 2", "Channel 1")
        result = self.run_audit(text)
        self.assertEqual(result["duplicate_names_in_m3u"], 1)
        self.assertEqual(result["status"], "INCONCLUSIVE")

    def test_wrong_count_defers(self):
        self.channels["entries"].pop()
        self.channels["total"] = 1
        self.assertEqual(self.run_audit()["status"], "DEFERRED")

    def test_incomplete_grid_blocks(self):
        self.channels["total"] = 3
        self.assertEqual(self.run_audit()["reason"], "INCOMPLETE_GRID")

    def test_unknown_tag_blocks(self):
        self.channels["entries"][0]["tags"] = ["missing"]
        self.assertEqual(self.run_audit()["reason"], "UNKNOWN_CHANNEL_TAG")

    def test_invalid_extinf_blocks(self):
        text = M3U.replace('group-title="B"', 'other="B"')
        self.assertEqual(self.run_audit(text)["reason"], "INVALID_EXTINF")

    def test_duplicate_tag_name_blocks(self):
        self.tags["entries"][1]["name"] = "A"
        self.assertEqual(self.run_audit()["reason"], "AMBIGUOUS_TAGS")

    def test_no_credentials_in_report(self):
        private_m3u = M3U.replace("http://example.invalid/1", "http://secret:password@example.invalid/1")
        result = self.run_audit(private_m3u)
        self.assertNotIn("password", repr(result))



class GroupNumberAuditTests(unittest.TestCase):
    def setUp(self):
        self.tags = {"total": 2, "entries": [
            {"uuid": "u1", "name": "A"},
            {"uuid": "u2", "name": "B"},
        ]}
        self.channels = {"total": 3, "entries": [
            {"uuid": "c1", "name": "Duplicated", "number": 1, "tags": ["u1"]},
            {"uuid": "c2", "name": "Duplicated", "number": 2, "tags": ["u2"]},
            {"uuid": "c3", "name": "Unique", "number": 3, "tags": ["u1"]},
        ]}
        self.m3u = """#EXTM3U
#EXTINF:-1 group-title="A" tvh-chnum="1",Duplicated
http://example.invalid/1
#EXTINF:-1 group-title="B" tvg-chno="2",Duplicated
http://example.invalid/2
#EXTINF:-1 group-title="A" tvh-chnum="3",Unique
http://example.invalid/3
"""

    def audit(self, playlist=None):
        return audit_with_numbers(self.m3u if playlist is None else playlist,
                                  self.tags, self.channels)

    def test_all_pairs_identified_without_write_authority(self):
        result = self.audit()
        self.assertEqual(result["exact_unique_name_pairs"], 1)
        self.assertEqual(result["number_disambiguated_pairs"], 2)
        self.assertEqual(result["resolved_pairs"], 3)
        self.assertEqual(result["group_mismatch_count"], 0)
        self.assertFalse(result["apply_authorized"])

    def test_wrong_group_detected(self):
        self.channels["entries"][1]["tags"] = ["u1"]
        result = self.audit()
        self.assertEqual(result["group_mismatch_count"], 1)

    def test_duplicate_name_and_number_unresolved(self):
        self.channels["entries"][1]["number"] = 1
        result = self.audit()
        self.assertEqual(result["status"], "INCONCLUSIVE")
        self.assertEqual(result["number_disambiguated_pairs"], 0)

    def test_missing_tvh_number_unresolved(self):
        self.channels["entries"][1].pop("number")
        self.assertEqual(self.audit()["unresolved_m3u_channels"], 1)

    def test_changed_number_unresolved(self):
        self.channels["entries"][1]["number"] = 20
        self.assertEqual(self.audit()["unresolved_m3u_channels"], 1)

    def test_decimal_number_normalization(self):
        self.channels["entries"][1]["number"] = "02.0"
        self.assertEqual(self.audit()["number_disambiguated_pairs"], 2)

    def test_conflicting_m3u_numbers_block(self):
        src = self.m3u.replace('tvh-chnum="1"', 'tvh-chnum="1" tvg-chno="9"')
        self.assertEqual(self.audit(src)["reason"], "CONFLICTING_CHANNEL_NUMBER")

    def test_credentials_not_in_result(self):
        src = self.m3u.replace("example.invalid/1", "secret:password@example.invalid/1")
        self.assertNotIn("password", repr(self.audit(src)))

    def test_no_number_does_not_guess_position(self):
        src = self.m3u.replace('tvh-chnum="1"', "")
        self.assertEqual(self.audit(src)["unresolved_m3u_channels"], 1)

    def test_incomplete_grid_blocks(self):
        self.channels["total"] = 900
        self.assertEqual(self.audit()["status"], "BLOCKED")

if __name__ == "__main__":
    unittest.main()
