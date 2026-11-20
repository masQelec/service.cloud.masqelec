"""G3-N registry + authenticated API adapter tests; all fixtures local."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import pvr_tag_ownership as R
from lib import pvr_tag_tvh_adapter as A


class OwnershipTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name) / "private"
        self.folder.mkdir(mode=0o700)
        self.file = self.folder / "owned.json"

    def test_missing_registry_is_empty(self):
        self.assertEqual(R.load(self.file), [])

    def test_atomic_roundtrip(self):
        uuids = ["a" * 32, "b" * 32]
        self.assertEqual(R.save(self.file, reversed(uuids)), uuids)
        self.assertEqual(R.load(self.file), uuids)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o600)

    def test_duplicate_uuid_rejected(self):
        with self.assertRaisesRegex(R.RegistryBlocked, "DUPLICATE"):
            R.save(self.file, ["a" * 32, "a" * 32])

    def test_untrusted_uuid_rejected(self):
        with self.assertRaisesRegex(R.RegistryBlocked, "INVALID_OWNED_UUID"):
            R.save(self.file, ["something-not-hex"])

    def test_symlink_registry_rejected(self):
        target = self.folder / "elsewhere"
        target.write_text("{}")
        self.file.symlink_to(target)
        with self.assertRaisesRegex(R.RegistryBlocked, "REGISTRY_SYMLINK"):
            R.load(self.file)

    def test_corrupt_registry_fails_closed(self):
        self.file.write_text("not-json")
        self.file.chmod(0o600)
        with self.assertRaisesRegex(R.RegistryBlocked, "REGISTRY_UNREADABLE"):
            R.load(self.file)

    def test_permissive_registry_directory_fails(self):
        self.folder.chmod(0o755)
        with self.assertRaisesRegex(R.RegistryBlocked, "REGISTRY_DIRECTORY_NOT_PRIVATE"):
            R.load(self.file)

    def test_not_adopting_previous_tags(self):
        # An absent registry never infers ownership from TVH inventory.
        self.assertEqual(R.load(self.file), [])

    def test_tampered_schema_fails(self):
        self.file.write_text(json.dumps({"version": 1, "uuids": [], "extra": []}))
        self.file.chmod(0o600)
        with self.assertRaisesRegex(R.RegistryBlocked, "REGISTRY_SCHEMA_INVALID"):
            R.load(self.file)


class AdapterTests(unittest.TestCase):
    def test_read_grids(self):
        seen = []
        def get_json(endpoint, query):
            seen.append(endpoint)
            return True, 200, {"total": 1, "entries": [{"uuid": "x"}]}, ""
        tags, channels = A.make_snapshot_reader(get_json)()
        self.assertEqual([tags["total"], channels["total"]], [1, 1])
        self.assertEqual(seen, ["channeltag/grid", "channel/grid"])

    def test_partial_inventory_blocked(self):
        def get_json(endpoint, query):
            return True, 200, {"total": 2, "entries": [{}]}, ""
        with self.assertRaisesRegex(A.TvheadendAPIBlocked, "TVH_PARTIAL_GRID"):
            A.make_snapshot_reader(get_json)()

    def test_get_http_failure(self):
        with self.assertRaisesRegex(A.TvheadendAPIBlocked, "TVH_READ_FAILED"):
            A.make_snapshot_reader(lambda e, query: (False, 401, None, ""))()

    def test_create_form_adapter(self):
        calls = []
        def post_form(endpoint, form):
            calls.append((endpoint, form))
            return True, 200, "{}"
        api = A.make_writer(post_form)
        self.assertTrue(api("channeltag/create", {
            "conf": json.dumps({"name": "New", "internal": False})
        }))
        self.assertEqual(calls[0][0], "channeltag/create")

    def test_write_error_blocks(self):
        api = A.make_writer(lambda e, f: (True, 200, '{"error":"denied"}'))
        with self.assertRaisesRegex(A.TvheadendAPIBlocked, "TVH_WRITE_REJECTED"):
            api("idnode/delete", {"uuid": "a" * 32})

    def test_unknown_endpoint_never_posted(self):
        def never(e, f):
            raise AssertionError("called")
        with self.assertRaisesRegex(A.TvheadendAPIBlocked, "NOT_ALLOWED"):
            A.make_writer(never)("idnode/save", {"uuid": "a" * 32})


if __name__ == "__main__":
    unittest.main()
