"""Regression tests for the G0 offline-only TV database inspector."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "pvr_g0_inspect_snapshot.py"
spec = importlib.util.spec_from_file_location("pvr_g0_inspect_snapshot", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class InspectG0Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "TV42.db"
        con = sqlite3.connect(str(self.path))
        con.executescript("""
            PRAGMA user_version=42;
            CREATE TABLE channels (idChannel INTEGER PRIMARY KEY, sChannelName TEXT);
            CREATE TABLE channelgroups (idGroup INTEGER PRIMARY KEY);
            CREATE TABLE map_channelgroups_channels (
                idGroup INTEGER REFERENCES channelgroups(idGroup),
                idChannel INTEGER REFERENCES channels(idChannel));
            INSERT INTO channels VALUES (1, 'Test');
        """)
        con.commit()
        con.close()

    def test_reads_schema_and_counts_without_mutation(self):
        before = self.path.read_bytes()
        info = module.inspect_snapshot(self.path)
        self.assertEqual(info["status"], "READ_ONLY")
        self.assertEqual(info["user_version"], 42)
        self.assertEqual(info["tables"]["channels"]["count"], 1)
        self.assertEqual(info["missing_expected_tables"], [])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(Path(str(self.path) + "-wal").exists())

    def test_missing_tables_are_reported_not_modified(self):
        con = sqlite3.connect(str(self.path))
        con.execute("DROP TABLE channelgroups")
        con.commit()
        con.close()
        info = module.inspect_snapshot(self.path)
        self.assertIn("channelgroups", info["missing_expected_tables"])

    def test_rejects_sidecars(self):
        Path(str(self.path) + "-wal").write_bytes(b"fake")
        with self.assertRaisesRegex(ValueError, "sidecars"):
            module.inspect_snapshot(self.path)

    def test_rejects_invalid_name(self):
        other = self.path.with_name("Other.db")
        other.write_bytes(self.path.read_bytes())
        with self.assertRaisesRegex(ValueError, "TV"):
            module.inspect_snapshot(other)

    def test_rejects_symlink(self):
        link = self.path.with_name("TV43.db")
        link.symlink_to(self.path)
        with self.assertRaisesRegex(ValueError, "symlink"):
            module.inspect_snapshot(link)

    def test_rejects_corrupt_header(self):
        self.path.write_bytes(b"?" * 200)
        with self.assertRaisesRegex(ValueError, "SQLite"):
            module.inspect_snapshot(self.path)


if __name__ == "__main__":
    unittest.main()
