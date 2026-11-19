"""Offline tests: no OneDrive, OAuth, FUSE or systemd required."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "strm_mount_path_gate.py"
spec = importlib.util.spec_from_file_location("strm_mount_path_gate", SCRIPT)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class MountPathGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.a = self.base / "a.strm"
        self.b = self.base / "b.strm"
        self.a.write_text("/mnt/cloud/a/movie.mkv\n", encoding="utf-8")
        self.b.write_text("/mnt/cloud/b/movie.mkv\n", encoding="utf-8")

    def manifest(self):
        return {"accounts": [
            {"id": "one", "old_mount": "/mnt/cloud/a",
             "new_mount": "/mnt/cloud/a", "sample_strm": [str(self.a)]},
            {"id": "two", "old_mount": "/mnt/cloud/b",
             "new_mount": "/mnt/cloud/b", "sample_strm": [str(self.b)]},
        ]}

    def test_two_accounts_match(self):
        self.assertEqual(gate.inspect_manifest(self.manifest()), [("one", 1), ("two", 1)])

    def test_reject_changed_mount(self):
        cfg = self.manifest()
        cfg["accounts"][1]["new_mount"] = "/mnt/another"
        with self.assertRaisesRegex(ValueError, "MOUNT_PATH_MISMATCH"):
            gate.inspect_manifest(cfg)

    def test_reject_swapped_mounts(self):
        cfg = self.manifest()
        cfg["accounts"][0]["new_mount"] = "/mnt/cloud/b"
        cfg["accounts"][1]["new_mount"] = "/mnt/cloud/a"
        with self.assertRaisesRegex(ValueError, "MOUNT_PATH_MISMATCH"):
            gate.inspect_manifest(cfg)

    def test_reject_cross_account_reference(self):
        self.a.write_text("/mnt/cloud/b/movie.mkv\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "STRM_MOUNT_PREFIX_MISMATCH"):
            gate.inspect_manifest(self.manifest())

    def test_reject_false_prefix(self):
        self.a.write_text("/mnt/cloud/a-other/movie.mkv\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "STRM_MOUNT_PREFIX_MISMATCH"):
            gate.inspect_manifest(self.manifest())

    def test_reject_remote_url(self):
        self.a.write_text("https://example.invalid/file.mkv\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "NONLOCAL_OR_NONCANONICAL_STRM"):
            gate.inspect_manifest(self.manifest())

    def test_accept_file_url(self):
        self.a.write_text("file:///mnt/cloud/a/movie.mkv\n", encoding="utf-8")
        self.assertEqual(len(gate.inspect_manifest(self.manifest())), 2)

    def test_reject_mount_collision(self):
        cfg = self.manifest()
        cfg["accounts"][1]["old_mount"] = "/mnt/cloud/a"
        cfg["accounts"][1]["new_mount"] = "/mnt/cloud/a"
        with self.assertRaisesRegex(ValueError, "MOUNT_COLLISION"):
            gate.inspect_manifest(cfg)

    def test_reject_missing_sample(self):
        self.b.unlink()
        with self.assertRaises(FileNotFoundError):
            gate.inspect_manifest(self.manifest())

    def test_reject_duplicate_sample(self):
        cfg = self.manifest()
        cfg["accounts"][1]["sample_strm"] = [str(self.a)]
        with self.assertRaisesRegex(ValueError, "SAMPLE_REUSED_ACROSS_ACCOUNTS"):
            gate.inspect_manifest(cfg)


if __name__ == "__main__":
    unittest.main()
