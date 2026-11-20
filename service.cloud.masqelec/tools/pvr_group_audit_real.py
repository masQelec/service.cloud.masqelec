#!/usr/bin/env python3
"""Read-only live TVH/M3U group audit; no external Python dependencies.

Run from repo checkout (uses ../lib/pvr_group_audit.py) or alongside
pvr_group_audit.py on CoreELEC. Never print playlist or raw API data.
"""
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request

PLAYLIST = Path("/storage/.user/playlist.m3u")
BASE = "http://127.0.0.1:9981/api/"
MAX_PLAYLIST_BYTES = 16 * 1024 * 1024
MAX_API_BYTES = 16 * 1024 * 1024


def _load_auditor():
    candidates = (
        Path(__file__).resolve().parent / "pvr_group_audit.py",
        Path(__file__).resolve().parent.parent / "lib" / "pvr_group_audit.py",
    )
    for candidate in candidates:
        if candidate.is_file():
            spec = importlib.util.spec_from_file_location("pvr_group_audit", candidate)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.audit_with_numbers
    raise RuntimeError("AUDITOR_MODULE_UNAVAILABLE")


def _grid(endpoint, limit):
    if endpoint not in ("channeltag/grid", "channel/grid"):
        raise ValueError("INVALID_API_ENDPOINT")
    url = BASE + endpoint + "?start=0&limit=" + str(limit) + "&all=1"
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "masQelec-G3-readonly"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise RuntimeError("TVH_HTTP_STATUS")
        raw = response.read(MAX_API_BYTES + 1)
    if len(raw) > MAX_API_BYTES:
        raise RuntimeError("TVH_RESPONSE_TOO_LARGE")
    payload = json.loads(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise RuntimeError("TVH_INVALID_GRID")
    if type(payload.get("total")) is not int or payload["total"] != len(payload["entries"]):
        raise RuntimeError("TVH_INCOMPLETE_GRID")
    return payload


def _read_playlist():
    if not PLAYLIST.is_file():
        raise RuntimeError("PLAYLIST_UNAVAILABLE")
    if PLAYLIST.stat().st_size > MAX_PLAYLIST_BYTES:
        raise RuntimeError("PLAYLIST_TOO_LARGE")
    with PLAYLIST.open("rb") as handle:
        raw = handle.read(MAX_PLAYLIST_BYTES + 1)
    if len(raw) > MAX_PLAYLIST_BYTES:
        raise RuntimeError("PLAYLIST_TOO_LARGE")
    return raw.decode("utf-8-sig")


def run():
    audit_with_numbers = _load_auditor()
    playlist = _read_playlist()
    tags = _grid("channeltag/grid", 200)
    channels = _grid("channel/grid", 20000)
    result = audit_with_numbers(playlist, tags, channels)
    print("=== G3-F INTEGRADO / SOLO LECTURA ===")
    for label, key in (
        ("RESULT", "status"),
        ("REASON", "reason"),
        ("M3U_CHANNELS", "m3u_channels"),
        ("TVH_CHANNELS", "tvh_channels"),
        ("EXACT_NAME_PAIRS", "exact_unique_name_pairs"),
        ("NAME_NUMBER_PAIRS", "number_disambiguated_pairs"),
        ("RESOLVED_PAIRS", "resolved_pairs"),
        ("UNRESOLVED", "unresolved_m3u_channels"),
        ("GROUP_MISMATCHES", "group_mismatch_count"),
    ):
        if key in result:
            print(label + "=" + str(result[key]))
    print("READ_ONLY=YES")
    print("APPLY_AUTHORIZED=NO")
    # A mismatch still produces a diagnostic, not a write operation.
    return 0 if result.get("status") == "DIAGNOSTIC_ONLY" and not result.get("group_mismatch_count") else 2


if __name__ == "__main__":
    try:
        sys.exit(run())
    except (Exception, KeyboardInterrupt) as exc:
        # Never print exception messages/tracebacks: they may contain URLs.
        print("RESULT=ERROR")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("READ_ONLY=YES")
        print("APPLY_AUTHORIZED=NO")
        sys.exit(2)
