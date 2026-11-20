"""Offline TV46 + TVH channel/grid comparison. Never permits deletions.
Only a candidate diagnostic; names are hints, not channel identities.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import re
import sqlite3


class DiagnosticBlocked(ValueError):
    pass


def _offline_db(path):
    path = Path(path).expanduser()
    if path.is_symlink():
        raise DiagnosticBlocked("SYMLINK_DB")
    p = path.resolve(strict=True)
    if not re.fullmatch(r"TV\d+\.db", p.name, re.I):
        raise DiagnosticBlocked("INVALID_DB_NAME")
    if ".kodi" in (x.lower() for x in p.parts) or "userdata" in (x.lower() for x in p.parts):
        raise DiagnosticBlocked("LIVE_DB_FORBIDDEN")
    if any(Path(str(p) + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise DiagnosticBlocked("SQLITE_SIDECAR")
    if not p.is_file() or p.stat().st_size < 100:
        raise DiagnosticBlocked("INVALID_DB")
    with p.open("rb") as fd:
        if fd.read(16) != b"SQLite format 3\x00":
            raise DiagnosticBlocked("NOT_SQLITE")
    return p


def _load_grid(path):
    p = Path(path)
    if p.is_symlink() or p.stat().st_size > 12 * 1024 * 1024:
        raise DiagnosticBlocked("INVALID_TVH_EXPORT")
    with p.open("r", encoding="utf-8") as fd:
        raw = json.load(fd)
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise DiagnosticBlocked("INVALID_GRID_SCHEMA")
    if raw.get("total") is not None and (
        not isinstance(raw["total"], int) or raw["total"] != len(raw["entries"])
    ):
        raise DiagnosticBlocked("TVH_GRID_PAGINATION_INCOMPLETE")
    entries = raw["entries"]
    if len(entries) > 20000 or not all(isinstance(e, dict) for e in entries):
        raise DiagnosticBlocked("INVALID_GRID_ENTRIES")
    uuids = [e.get("uuid") for e in entries]
    if any(not isinstance(v, str) or not v for v in uuids) or len(set(uuids)) != len(uuids):
        raise DiagnosticBlocked("INVALID_OR_DUPLICATE_TVH_UUID")
    return entries


def analyze(offline_db, tvh_grid_json):
    p = _offline_db(offline_db)
    grid = _load_grid(tvh_grid_json)
    con = sqlite3.connect(p.as_uri() + "?mode=ro", uri=True, timeout=1.0)
    try:
        con.execute("PRAGMA query_only=ON")
        con.execute("PRAGMA busy_timeout=1000")
        if con.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise DiagnosticBlocked("SQLITE_INTEGRITY_FAILED")
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        required = {"version", "channels", "channelgroups", "map_channelgroups_channels", "clients"}
        if not required <= tables:
            raise DiagnosticBlocked("UNKNOWN_SQLITE_SCHEMA")
        version = [r[0] for r in con.execute("SELECT idVersion FROM version")]
        if version != [46]:
            raise DiagnosticBlocked("SCHEMA_NOT_TV46")
        clients = con.execute("SELECT idClient,sAddonID FROM clients").fetchall()
        pvr_ids = [id_ for id_, addon in clients if addon == "pvr.hts"]
        if len(pvr_ids) != 1:
            raise DiagnosticBlocked("AMBIGUOUS_PVR_HTS_CLIENT")
        client_id = pvr_ids[0]
        channels = con.execute(
            "SELECT idChannel,iUniqueId,sChannelName,bIsRadio FROM channels WHERE iClientId=?",
            (client_id,)
        ).fetchall()
        if len(set(c[1] for c in channels)) != len(channels):
            raise DiagnosticBlocked("DUPLICATE_KODI_UID")
        groups = con.execute(
            "SELECT idGroup,iGroupType,iClientId,sClientName FROM channelgroups"
        ).fetchall()
        internal_ids = {r[0] for r in groups if r[1] == 1 and r[2] == -1}
        external_ids = {r[0] for r in groups if r[2] == client_id and r[1] == 0}
        if internal_ids & external_ids:
            raise DiagnosticBlocked("AMBIGUOUS_GROUP_CLASSIFICATION")
        group_links = con.execute(
            "SELECT idGroup,idChannel FROM map_channelgroups_channels"
        ).fetchall()
        channel_pk = {r[0] for r in channels}
        if any(cid not in channel_pk for _, cid in group_links):
            raise DiagnosticBlocked("UNKNOWN_OR_DANGLING_CHANNEL_LINKS")
        # Exact names can help manual review only, never authorize identity mapping.
        kodi_names = Counter(r[2] for r in channels if isinstance(r[2], str) and r[2])
        tvh_names = Counter(
            e.get("name") for e in grid if isinstance(e.get("name"), str) and e["name"]
        )
        unique_names_both = sum(
            1 for name, n in kodi_names.items() if n == 1 and tvh_names[name] == 1
        )
        return {
            "status": "G2_OFFLINE_DIAGNOSTIC_ONLY",
            "kodi_database_version": 46,
            "kodi_client_id": client_id,
            "kodi_channels": len(channels),
            "tvh_grid_channels": len(grid),
            "kodi_groups_external": len(external_ids),
            "kodi_groups_internal": len(internal_ids),
            "kodi_internal_group_id_one": 1 in internal_ids,
            "kodi_external_group_id_one": 1 in external_ids,
            "kodi_duplicate_name_values": sum(1 for n in kodi_names.values() if n > 1),
            "tvh_duplicate_name_values": sum(1 for n in tvh_names.values() if n > 1),
            "tvh_channels_without_name": sum(not e.get("name") for e in grid),
            "unique_exact_name_matches_HINT_ONLY": unique_names_both,
            "identity_mapping_verified": False,
            "orphan_count_verified": None,
            "destructive_operations_authorized": False,
        }
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("offline_db")
    parser.add_argument("tvh_grid_json")
    args = parser.parse_args()
    try:
        print(json.dumps(analyze(args.offline_db, args.tvh_grid_json), indent=2, sort_keys=True))
    except (DiagnosticBlocked, ValueError, OSError, sqlite3.Error) as exc:
        # No untrusted paths, names, URLs, or HTTP payloads printed.
        reason = str(exc) if isinstance(exc, DiagnosticBlocked) else type(exc).__name__
        print(json.dumps({"status": "G2_BLOCKED", "reason": reason,
                          "destructive_operations_authorized": False}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
