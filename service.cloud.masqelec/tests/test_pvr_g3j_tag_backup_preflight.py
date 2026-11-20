"""G3-J checks in temporary directories, without TVH/Kodi writes."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3j_tag_backup_preflight.py"
SPEC = importlib.util.spec_from_file_location("pvr_g3j_tag_backup_preflight", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)

class BackupPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "tvh"
        self.tags = self.root / "channel" / "tag"
        self.tags.mkdir(parents=True)
        self.backups = Path(self.tmp.name) / "private"
        (self.tags / M.UUID).write_text(json.dumps({
            "name": M.NAME, "internal": False, "enabled": True, "index": 0
        }), encoding="utf-8")
        self.patches = [
            patch.object(M, "TAGDIR", self.tags),
            patch.object(M, "TVH_CONFIG", self.root),
            patch.object(M, "BACKUP_ROOT", self.backups),
        ]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def test_byte_exact_private_backup(self):
        saved, digest = M._backup_tag()
        self.assertEqual(saved.read_bytes(), (self.tags / M.UUID).read_bytes())
        self.assertEqual(len(digest), 64)
        self.assertEqual(saved.stat().st_mode & 0o777, 0o600)

    def test_wrong_name_denied(self):
        (self.tags / M.UUID).write_text('{"name":"Wrong","internal":false}')
        with self.assertRaisesRegex(ValueError, "TAG_IDENTITY_MISMATCH"):
            M._backup_tag()

    def test_internal_denied(self):
        (self.tags / M.UUID).write_text(json.dumps({
            "name": M.NAME, "internal": True
        }))
        with self.assertRaisesRegex(ValueError, "TAG_IDENTITY_MISMATCH"):
            M._backup_tag()

    def test_symlink_tag_denied(self):
        other = Path(self.tmp.name) / "other"
        other.write_text('{"name":"ES - NBA","internal":false}')
        (self.tags / M.UUID).unlink()
        (self.tags / M.UUID).symlink_to(other)
        with self.assertRaisesRegex(ValueError, "INVALID_OR_OVERSIZE_TAG"):
            M._backup_tag()

    def test_reference_scan_find_uuid(self):
        path = self.root / "dvr"
        path.mkdir()
        (path / "a").write_text("reference=" + M.UUID)
        hits, scanned, bad, skipped = M._scan_references()
        self.assertEqual(hits, 1)
        self.assertEqual(bad, 0)

    def test_empty_reference_scan(self):
        hits, scanned, bad, skipped = M._scan_references()
        self.assertEqual((hits, bad, skipped), (0, 0, 0))

    def test_reference_scan_file_limit_denied(self):
        # The target tag is deliberately excluded from the scan.
        # Add a second file so the scan really exceeds a zero-file limit.
        extra = self.root / "dvr" / "independent"
        extra.parent.mkdir(parents=True)
        extra.write_text("unrelated configuration", encoding="utf-8")
        with patch.object(M, "MAX_SCAN_FILES", 0):
            with self.assertRaisesRegex(ValueError, "REFERENCE_SCAN_LIMIT_FILES"):
                M._scan_references()

    def test_large_file_full_scan_without_truncation(self):
        folder = self.root / "dvr"
        folder.mkdir()
        (folder / "large").write_bytes(b"x" * (M.MAX_FILE + 256))
        hits, scanned, unreadable, skipped = M._scan_references()
        self.assertEqual((hits, unreadable, skipped), (0, 0, 0))

    def test_reference_beyond_first_megabyte(self):
        folder = self.root / "dvr"
        folder.mkdir()
        (folder / "large").write_bytes(b"x" * (M.MAX_FILE + 256) + M.UUID.encode())
        hits, _, unreadable, skipped = M._scan_references()
        self.assertEqual((hits, unreadable, skipped), (1, 0, 0))

    def test_reference_split_across_read_boundary(self):
        folder = self.root / "dvr"
        folder.mkdir()
        (folder / "split").write_bytes(b"x" * (64 * 1024 - 10) + M.UUID.encode())
        hits, _, unreadable, skipped = M._scan_references()
        self.assertEqual((hits, unreadable, skipped), (1, 0, 0))

    def test_scan_only_does_not_create_another_backup(self):
        from contextlib import redirect_stdout
        from io import StringIO
        import sys
        with patch.object(sys, "argv", ["tool.py", "--scan-only"]), \
             patch.object(M, "_backup_tag", side_effect=AssertionError("backup invoked")):
            with redirect_stdout(StringIO()) as buffer:
                code = M.main()
        self.assertEqual(code, 0)
        self.assertIn("BACKUP_CREATED=NO", buffer.getvalue())

if __name__ == "__main__":
    unittest.main()
