"""G3-C fail-closed planner tests. No TVH server required."""
import unittest
from lib.pvr_tag_plan import PlanBlocked, m3u_groups, plan


PLAYLIST = '#EXTM3U\n#EXTINF:-1 group-title="B",One\nhttp://invalid.test/1\n#EXTINF:-1 group-title="A",Two\nhttp://invalid.test/2\n'


class TagPlanTests(unittest.TestCase):
    def setUp(self):
        self.tags = {"total": 3, "entries": [
            {"uuid": "u1", "name": "A", "index": 0, "internal": False},
            {"uuid": "u2", "name": "B", "index": 0, "internal": False},
            {"uuid": "old", "name": "Old", "index": 0, "internal": False},
        ]}
        self.channels = {"total": 2, "entries": [
            {"uuid": "c1", "tags": ["u2"]},
            {"uuid": "c2", "tags": ["u1"]},
        ]}

    def test_order_preserved_and_unowned_not_deleted(self):
        result = plan(PLAYLIST, self.tags, self.channels)
        self.assertEqual(m3u_groups(PLAYLIST), (["B", "A"], 2))
        self.assertEqual([r["uuid"] for r in result["reorder_candidates"]], ["u2", "u1"])
        self.assertEqual(result["delete_owned_empty_candidates"], [])
        self.assertEqual(result["preserved_unowned_or_internal_empty"], ["old"])
        self.assertFalse(result["apply_authorized"])

    def test_explicit_owned_empty_candidate(self):
        result = plan(PLAYLIST, self.tags, self.channels, {"old"})
        self.assertEqual(result["delete_owned_empty_candidates"], ["old"])
        self.assertFalse(result["apply_authorized"])

    def test_renamed_group_is_not_deletion_without_ownership(self):
        self.tags["entries"][2]["name"] = "Another historical name"
        result = plan(PLAYLIST, self.tags, self.channels)
        self.assertEqual(result["delete_owned_empty_candidates"], [])

    def test_tag_with_active_channel_is_never_deleted(self):
        self.channels["entries"][0]["tags"].append("old")
        result = plan(PLAYLIST, self.tags, self.channels, {"old"})
        self.assertEqual(result["delete_owned_empty_candidates"], [])

    def test_internal_tag_is_never_deleted(self):
        self.tags["entries"][2]["internal"] = True
        result = plan(PLAYLIST, self.tags, self.channels, {"old"})
        self.assertEqual(result["delete_owned_empty_candidates"], [])

    def test_delayed_tvh_refetch_blocks(self):
        self.channels["total"] = 1
        self.channels["entries"] = self.channels["entries"][:1]
        with self.assertRaisesRegex(PlanBlocked, "REFETCH_NOT_CONVERGED"):
            plan(PLAYLIST, self.tags, self.channels)

    def test_partial_grid_blocks(self):
        self.tags["total"] = 5
        with self.assertRaisesRegex(PlanBlocked, "INCOMPLETE_INVENTORY"):
            plan(PLAYLIST, self.tags, self.channels)

    def test_duplicate_name_blocks(self):
        self.tags["entries"][2]["name"] = "B"
        with self.assertRaisesRegex(PlanBlocked, "AMBIGUOUS_TAG_NAMES"):
            plan(PLAYLIST, self.tags, self.channels)

    def test_unresolvable_reference_blocks(self):
        self.channels["entries"][1]["tags"] = ["missing"]
        with self.assertRaisesRegex(PlanBlocked, "UNKNOWN_CHANNEL_TAG_REFERENCE"):
            plan(PLAYLIST, self.tags, self.channels)

    def test_empty_assignment_blocks(self):
        self.channels["entries"][1]["tags"] = []
        with self.assertRaisesRegex(PlanBlocked, "UNTAGGED_CHANNELS"):
            plan(PLAYLIST, self.tags, self.channels)

    def test_missing_group_blocks(self):
        with self.assertRaisesRegex(PlanBlocked, "MISSING_GROUP_TITLE"):
            plan("#EXTM3U\n#EXTINF:-1,Channel\nurl\n", self.tags, self.channels)

    def test_stale_registry_blocks(self):
        with self.assertRaisesRegex(PlanBlocked, "STALE_OWNERSHIP_REGISTRY"):
            plan(PLAYLIST, self.tags, self.channels, {"unknown"})

    def test_new_group_is_create_only(self):
        self.tags["entries"] = self.tags["entries"][:2]
        self.tags["total"] = 2
        src = PLAYLIST + '#EXTINF:-1 group-title="C",Three\nhttp://invalid.test/3\n'
        self.channels["entries"].append({"uuid": "c3", "tags": ["u2"]})
        self.channels["total"] = 3
        self.assertEqual(plan(src, self.tags, self.channels)["create_names"], ["C"])


if __name__ == "__main__":
    unittest.main()
