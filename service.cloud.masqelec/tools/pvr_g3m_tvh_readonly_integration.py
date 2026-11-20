#!/usr/bin/env python3
"""G3-M: real TVH API + M3U read-only integration gate.

Reads existing M3U and TVH grids. Never sends POST, never prints URLs,
credentials, channels, or playlist text. Reports the dry-run planner result.
"""
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib.pvr_tag_plan import plan, PlanBlocked

PLAYLIST = Path("/storage/.user/playlist.m3u")
API = "http://127.0.0.1:9981/api/"
MAX_M3U = 16 * 1024 * 1024
MAX_RESPONSE = 24 * 1024 * 1024
GRID_LIMITS = {"channeltag/grid": 200, "channel/grid": 20000}


def _read_m3u():
    with PLAYLIST.open("rb") as stream:
        data = stream.read(MAX_M3U + 1)
    if len(data) > MAX_M3U:
        raise ValueError("M3U_TOO_LARGE")
    return data.decode("utf-8-sig")


def _grid(endpoint):
    if endpoint not in GRID_LIMITS:
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    query = urllib.parse.urlencode({
        "start": 0, "limit": GRID_LIMITS[endpoint], "all": 1
    })
    req = urllib.request.Request(
        API + endpoint + "?" + query, method="GET",
        headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status != 200:
            raise ValueError("TVH_HTTP_ERROR")
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("TVH_RESPONSE_TOO_LARGE")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("INVALID_GRID_RESPONSE")
    return value


def diagnose():
    playlist = _read_m3u()
    tags = _grid("channeltag/grid")
    channels = _grid("channel/grid")
    result = plan(playlist, tags, channels)
    # Recheck total to catch obvious mid-read mutations.
    tags2 = _grid("channeltag/grid")
    channels2 = _grid("channel/grid")
    if tags != tags2 or channels != channels2:
        raise PlanBlocked("INVENTORY_DRIFT")
    print("=== G3-M READ-ONLY TVH INTEGRATION ===")
    print("M3U_CHANNELS=" + str(result["m3u_channels"]))
    print("TVH_CHANNELS=" + str(result["tvh_channels"]))
    print("M3U_GROUPS=" + str(result["desired_groups"]))
    print("TVH_TAGS=" + str(result["existing_groups"]))
    print("GROUPS_TO_CREATE=" + str(len(result["create_names"])))
    print("GROUPS_TO_REORDER_DIAGNOSTIC=" + str(len(result["reorder_candidates"])))
    print("OWNED_EMPTY_TO_DELETE=" + str(len(result["delete_owned_empty_candidates"])))
    print("UNOWNED_OR_PROTECTED_EMPTY=" + str(len(result["preserved_unowned_or_internal_empty"])))
    print("SNAPSHOT_STABLE=YES")
    print("API_WRITE_EXECUTED=NO")
    print("AUTOMATIC_INTEGRATION_ACTIVE=NO")
    print("HISTORIC_DELETE_AUTHORIZED=NO")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(diagnose())
    except (Exception, KeyboardInterrupt) as exc:
        print("G3M=BLOCKED")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("API_WRITE_EXECUTED=NO")
        print("HISTORIC_DELETE_AUTHORIZED=NO")
        sys.exit(2)
