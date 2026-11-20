"""Unit tests for the isolated G3-L API reconciler; zero network/filesystem writes."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.pvr_tag_reconcile import reconcile_once, ReconcileBlocked
from lib.pvr_tag_plan import PlanBlocked


PLAYLIST = '#EXTM3U\n#EXTINF:-1 group-title="A",One\nurl1\n#EXTINF:-1 group-title="B",Two\nurl2\n'


class FakeTVH:
    def __init__(self):
        self.tags = [
            {"uuid": "a", "name": "A", "internal": False},
            {"uuid": "old", "name": "Old", "internal": False},
        ]
        self.channels = [{"uuid": "c1", "tags": ["a"]},
                         {"uuid": "c2", "tags": ["a"]}]
        self.actions = []
        self.fail = False

    def snapshot(self):
        return (
            {"entries": copy.deepcopy(self.tags), "total": len(self.tags)},
            {"entries": copy.deepcopy(self.channels), "total": len(self.channels)}
        )

    def post(self, path, params):
        if self.fail:
            return False
        self.actions.append((path, params))
        if path == "channeltag/create":
            import json
            name = json.loads(params["conf"])["name"]
            self.tags.append({"uuid": "new-" + name, "name": name,
                              "internal": False})
        elif path == "idnode/delete":
            self.tags = [x for x in self.tags if x["uuid"] != params["uuid"]]
        else:
            raise AssertionError("unknown action")
        return True


class TagReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tvh = FakeTVH()

    def cycle(self, owned=(), delete=False):
        return reconcile_once(PLAYLIST, self.tvh.snapshot,
                              self.tvh.post, owned, delete)

    def test_create_by_api_without_deleting_old_tag(self):
        outcome = self.cycle()
        self.assertEqual(outcome["status"], "CREATED")
        self.assertEqual(outcome["uuid"], "new-B")
        self.assertEqual([x[0] for x in self.tvh.actions], ["channeltag/create"])
        self.assertTrue(outcome["ownership_persistence_required"])
        self.assertFalse(outcome["delete_authorized"])
        self.assertTrue(any(t["uuid"] == "old" for t in self.tvh.tags))

    def test_second_cycle_idempotent(self):
        first = self.cycle()
        second = self.cycle(first["owned_tag_uuids"])
        self.assertEqual(second["status"], "UNCHANGED")
        self.assertEqual(len(self.tvh.actions), 1)

    def test_unowned_empty_never_deleted(self):
        self.cycle()
        self.assertEqual(self.cycle(["new-B"], delete=True)["status"], "UNCHANGED")
        self.assertEqual(len(self.tvh.actions), 1)

    def test_owned_empty_requires_explicit_enable(self):
        self.cycle()
        result = self.cycle(["new-B", "old"])
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(result["delete_candidates"], ["old"])
        self.assertEqual(len(self.tvh.actions), 1)

    def test_owned_empty_deleted_only_with_enable(self):
        self.cycle()
        result = self.cycle(["new-B", "old"], delete=True)
        self.assertEqual(result["status"], "DELETED")
        self.assertEqual(result["uuid"], "old")
        self.assertEqual(len(self.tvh.actions), 2)
        self.assertEqual(result["owned_tag_uuids"], ["new-B"])

    def test_active_old_tag_never_deleted(self):
        self.cycle()
        self.tvh.channels[0]["tags"].append("old")
        result = self.cycle(["new-B", "old"], delete=True)
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(len(self.tvh.actions), 1)

    def test_delayed_refetch_blocks_all_writes(self):
        self.tvh.channels.pop()
        with self.assertRaisesRegex(PlanBlocked, "REFETCH_NOT_CONVERGED"):
            self.cycle(delete=True)
        self.assertFalse(self.tvh.actions)

    def test_stale_registry_blocks_all_writes(self):
        with self.assertRaisesRegex(PlanBlocked, "STALE_OWNERSHIP_REGISTRY"):
            self.cycle(["unknown"], delete=True)
        self.assertFalse(self.tvh.actions)

    def test_failed_create_not_reported_success(self):
        self.tvh.fail = True
        with self.assertRaisesRegex(ReconcileBlocked, "CREATE_FAILED"):
            self.cycle()
        self.assertFalse(self.tvh.actions)

    def test_racing_inventory_blocks_write(self):
        counter = [0]
        def racing():
            counter[0] += 1
            if counter[0] == 2:
                self.tvh.tags.append({"uuid": "concurrent", "name": "Third",
                                      "internal": False})
            return self.tvh.snapshot()
        with self.assertRaisesRegex(ReconcileBlocked, "INVENTORY_CHANGED"):
            reconcile_once(PLAYLIST, racing, self.tvh.post)
        self.assertFalse(self.tvh.actions)

    def test_unexpected_tag_after_create_blocks(self):
        def corrupt_post(path, params):
            self.tvh.post(path, params)
            self.tvh.tags.append({"uuid": "foreign", "name": "Foreign",
                                  "internal": False})
            return True
        with self.assertRaisesRegex(ReconcileBlocked, "UNEXPECTED_TAG_INVENTORY_CHANGE"):
            reconcile_once(PLAYLIST, self.tvh.snapshot, corrupt_post)

    def test_duplicate_names_block_before_write(self):
        self.tvh.tags.append({"uuid": "a2", "name": "A", "internal": False})
        with self.assertRaisesRegex(PlanBlocked, "AMBIGUOUS_TAG_NAMES"):
            self.cycle()
        self.assertFalse(self.tvh.actions)

    def test_create_priority_over_delete(self):
        self.cycle(owned=["old"], delete=True)
        self.assertEqual([x[0] for x in self.tvh.actions], ["channeltag/create"])


if __name__ == "__main__":
    unittest.main()
