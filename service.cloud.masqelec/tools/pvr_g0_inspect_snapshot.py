#!/usr/bin/env python3
"""G0: inspect an OFFLINE copy of Kodi's TV database; no Kodi/TVH writes."""
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import sys

TV_DB = re.compile(r"^TV[0-9]+\.db$", re.IGNORECASE)
TABLES = ("channels", "channelgroups", "map_channelgroups_channels")


def inspect_snapshot(path):
    p = Path(path).expanduser()
    if p.is_symlink():
        raise ValueError("snapshot must not be a symlink")
    resolved = p.resolve(strict=True)
    if not TV_DB.fullmatch(resolved.name):
        raise ValueError("expected an offline copy named TV<number>.db")
    # Never inspect a Kodi database in its live directory.
    parts = tuple(x.lower() for x in resolved.parts)
    if ".kodi" in parts or "userdata" in parts or "/storage/.kodi/" in str(resolved).lower():
        raise ValueError("live Kodi paths are forbidden; provide an offline copy")
    if not resolved.is_file():
        raise ValueError("snapshot is not a regular file")
    if any(Path(str(resolved) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise ValueError("snapshot has SQLite sidecars: require a consistent closed copy")
    if resolved.stat().st_size < 100:
        raise ValueError("snapshot is too small")
    with resolved.open("rb") as f:
        if f.read(16) != b"SQLite format 3\x00":
            raise ValueError("not a SQLite database")
    # mode=ro plus query_only; no CREATE, VACUUM, checkpoint or writes.
    uri = resolved.as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=1.0)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=1000")
        integrity = con.execute("PRAGMA quick_check").fetchone()[0]
        tables = {
            name for (name,) in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ) if not name.startswith("sqlite_")
        }
        result = {
            "status": "READ_ONLY",
            "file": resolved.name,
            "size_bytes": resolved.stat().st_size,
            "integrity": integrity,
            "user_version": con.execute("PRAGMA user_version").fetchone()[0],
            "journal_mode": con.execute("PRAGMA journal_mode").fetchone()[0],
            "tables": {},
            "missing_expected_tables": sorted(set(TABLES) - tables),
        }
        for table in sorted(tables):
            # Table names come from sqlite_master; only quote escaped identifier.
            q = '"' + table.replace('"', '""') + '"'
            columns = [
                {"name": row[1], "type": row[2], "not_null": bool(row[3]), "pk": row[5]}
                for row in con.execute("PRAGMA table_info(" + q + ")")
            ]
            foreign_keys = [
                {"table": row[2], "from": row[3], "to": row[4], "on_delete": row[6]}
                for row in con.execute("PRAGMA foreign_key_list(" + q + ")")
            ]
            indices = [
                {"name": row[1], "unique": bool(row[2])}
                for row in con.execute("PRAGMA index_list(" + q + ")")
            ]
            result["tables"][table] = {
                "count": con.execute("SELECT COUNT(*) FROM " + q).fetchone()[0],
                "columns": columns,
                "foreign_keys": foreign_keys,
                "indices": indices,
            }
        return result
    finally:
        con.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", help="Offline, consistent TVxx.db copy; NEVER live Kodi DB")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(inspect_snapshot(args.snapshot), indent=2, sort_keys=True))
        return 0
    except (OSError, sqlite3.Error, ValueError) as exc:
        # Do not echo input path; it may contain private account details.
        print("G0_BLOCKED: " + type(exc).__name__, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
