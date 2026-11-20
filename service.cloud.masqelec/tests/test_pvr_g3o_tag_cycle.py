"""G3-O transactional cycle tests (mock TVH, private temporary storage)."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.pvr_tag_cycle import run_cycle, CycleBlocked
from lib.pvr_tag_ownership import load, save
from lib.pvr_tag_reconcile import ReconcileBlocked

PLAYLIST = '#EXTM3U\n#EXTINF:-1 group-title="A",One\nurl1\n#EXTINF:-1 group-title="B",Two\nurl2\n'
UID = "b" * 32
OLD = "c" * 32


class Fake:
    def __init__(self):
        self.tags = [{"uuid": "a" * 32, "name": "A", "internal": False},
                     {"uuid": OLD, "name": "Old", "internal": False}]
        self.channels = [{"uuid": "1", "tags": ["a" * 32]},
                         {"uuid": "2", "tags": ["a" * 32]}]
        self.posts = []
        self.fail_after_write = False

    def snapshot(self):
        return ({"entries": copy.deepcopy(self.tags), "total": len(self.tags)},
                {"entries": copy.deepcopy(self.channels), "total": len(self.channels)})

    def post(self, endpoint, fields):
        self.posts.append(endpoint)
        if endpoint == "channeltag/create":
            self.tags.append({"uuid": UID, "name": "B", "internal": False})
        elif endpoint == "idnode/delete":
            self.tags = [t for t in self.tags if t["uuid"] != fields["uuid"]]
        if self.fail_after_write:
            raise TimeoutError("response lost")
        return True


class CycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name) / "private"
        self.folder.mkdir(mode=0o700)
        self.fake = Fake()

    def cycle(self, **kw):
        return run_cycle(PLAYLIST, self.fake.snapshot, self.fake.post, self.folder, **kw)

    def test_dry_run_never_posts(self):
        result = self.cycle()
        self.assertEqual(result["status"], "DRY_RUN")
        self.assertEqual(result["creates"], ["B"])
        self.assertEqual(self.fake.posts, [])
        self.assertFalse((self.folder / "pending-tvhtag.json").exists())

    def test_create_commits_registry_then_clears_journal(self):
        result = self.cycle(apply=True)
        self.assertEqual(result["status"], "CREATED")
        self.assertEqual(load(self.folder / "owned-tvhtags.json"), [UID])
        self.assertFalse((self.folder / "pending-tvhtag.json").exists())
        self.assertEqual(self.fake.posts, ["channeltag/create"])

    def test_second_cycle_no_mutation(self):
        self.cycle(apply=True)
        result = self.cycle(apply=True)
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(len(self.fake.posts), 1)

    def test_historic_unowned_preserved_even_when_delete_enabled(self):
        self.cycle(apply=True)
        result = self.cycle(apply=True, allow_delete=True)
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(len(self.fake.posts), 1)
        self.assertIn(OLD, {t["uuid"] for t in self.fake.tags})

    def test_journal_remains_on_response_loss_and_blocks_retry(self):
        self.fake.fail_after_write = True
        with self.assertRaises(TimeoutError):
            self.cycle(apply=True)
        self.assertTrue((self.folder / "pending-tvhtag.json").exists())
        self.assertEqual(self.fake.posts, ["channeltag/create"])
        with self.assertRaisesRegex(CycleBlocked, "PENDING_OPERATION"):
            self.cycle(apply=True)
        self.assertEqual(len(self.fake.posts), 1)

    def test_persisted_journal_blocks_even_dry_run(self):
        (self.folder / "pending-tvhtag.json").write_text('{"version":1}')
        with self.assertRaisesRegex(CycleBlocked, "PENDING_OPERATION"):
            self.cycle()
        self.assertFalse(self.fake.posts)

    def test_invalid_registry_blocks_before_write(self):
        path = self.folder / "owned-tvhtags.json"
        path.write_text("{broken")
        path.chmod(0o600)
        with self.assertRaises(ValueError):
            self.cycle(apply=True)
        self.assertFalse(self.fake.posts)

    def test_delete_owned_empty_only_explicitly_enabled(self):
        self.cycle(apply=True)
        save(self.folder / "owned-tvhtags.json", [UID, OLD])
        self.assertEqual(self.cycle(apply=True)["status"], "UNCHANGED")
        result = self.cycle(apply=True, allow_delete=True)
        self.assertEqual(result["status"], "DELETED")
        self.assertEqual(load(self.folder / "owned-tvhtags.json"), [UID])
        self.assertFalse((self.folder / "pending-tvhtag.json").exists())

    def test_occupied_owned_never_deleted(self):
        self.cycle(apply=True)
        save(self.folder / "owned-tvhtags.json", [UID, OLD])
        self.fake.channels[0]["tags"].append(OLD)
        result = self.cycle(apply=True, allow_delete=True)
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(self.fake.posts, ["channeltag/create"])

    def test_directory_not_private_rejected(self):
        self.folder.chmod(0o755)
        with self.assertRaises(ValueError):
            self.cycle(apply=True)
        self.assertFalse(self.fake.posts)


if __name__ == "__main__":
    unittest.main()
