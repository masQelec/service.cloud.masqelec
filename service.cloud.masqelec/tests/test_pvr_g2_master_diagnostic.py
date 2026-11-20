"""Tests for the master G2 offline diagnostic; synthetic SQLite and TVH grid."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "pvr_g2_master_diagnostic.py"
spec = importlib.util.spec_from_file_location("pvr_g2_master_diagnostic", SCRIPT)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
spec.loader.exec_module(mod)


class G2MasterDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / "TV46.db"
        self.grid = Path(self.temp.name) / "grid.json"
        con = sqlite3.connect(self.db)
        con.executescript("""
        CREATE TABLE version(idVersion INTEGER);
        INSERT INTO version VALUES (46);
        CREATE TABLE clients(idClient INTEGER, sAddonID TEXT);
        INSERT INTO clients VALUES (1,'pvr.hts');
        CREATE TABLE channels(idChannel INTEGER, iUniqueId INTEGER,
                              sChannelName TEXT, bIsRadio INTEGER, iClientId INTEGER);
        INSERT INTO channels VALUES (11,111,'Same',0,1),(12,222,'Same',0,1);
        CREATE TABLE channelgroups(idGroup INTEGER, iGroupType INTEGER,
                                   iClientId INTEGER, sClientName TEXT);
        INSERT INTO channelgroups VALUES (1,0,1,'Real'),(27,1,-1,'');
        CREATE TABLE map_channelgroups_channels(idGroup INTEGER,idChannel INTEGER);
        INSERT INTO map_channelgroups_channels VALUES (1,11),(27,11),(27,12);
        """)
        con.commit()
        con.close()
        self.entries = [
            {"uuid": "a1", "name": "Same"},
            {"uuid": "b2", "name": "Other"},
        ]
        self.write_grid()

    def write_grid(self, total=None):
        self.grid.write_text(json.dumps({
            "total": len(self.entries) if total is None else total,
            "entries": self.entries
        }), encoding="utf-8")

    def test_group_one_is_external_and_no_deletions(self):
        report = mod.analyze(self.db, self.grid)
        self.assertTrue(report["kodi_external_group_id_one"])
        self.assertFalse(report["kodi_internal_group_id_one"])
        self.assertEqual(report["kodi_groups_internal"], 1)
        self.assertFalse(report["destructive_operations_authorized"])
        self.assertIsNone(report["orphan_count_verified"])

    def test_duplicate_names_cannot_match(self):
        report = mod.analyze(self.db, self.grid)
        self.assertEqual(report["kodi_duplicate_name_values"], 1)
        self.assertEqual(report["unique_exact_name_matches_HINT_ONLY"], 0)
        self.assertNotIn("Same", repr(report))

    def test_incomplete_grid_denied(self):
        self.write_grid(total=9)
        with self.assertRaises(mod.DiagnosticBlocked):
            mod.analyze(self.db, self.grid)

    def test_duplicate_uuid_denied(self):
        self.entries[1]["uuid"] = "a1"
        self.write_grid()
        with self.assertRaises(mod.DiagnosticBlocked):
            mod.analyze(self.db, self.grid)

    def test_live_kodi_path_denied(self):
        path = Path(self.temp.name) / ".kodi" / "userdata" / "Database" / "TV46.db"
        path.parent.mkdir(parents=True)
        path.write_bytes(self.db.read_bytes())
        with self.assertRaises(mod.DiagnosticBlocked):
            mod.analyze(path, self.grid)

    def test_wrong_schema_denied(self):
        con = sqlite3.connect(self.db)
        con.execute("UPDATE version SET idVersion=47")
        con.commit()
        con.close()
        with self.assertRaises(mod.DiagnosticBlocked):
            mod.analyze(self.db, self.grid)


if __name__ == "__main__":
    unittest.main()
