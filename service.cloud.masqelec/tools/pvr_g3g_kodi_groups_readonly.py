#!/usr/bin/env python3
"""G3-G: compare ordered M3U, TVH tag indices, and Kodi PVR group order.

Read-only HTTP GET to TVH and JSON-RPC ReadData to Kodi. No config writes.
"""
import json
from pathlib import Path
import re
import sys
import urllib.request
import urllib.error

PLAYLIST = Path("/storage/.user/playlist.m3u")
TVH_API = "http://127.0.0.1:9981/api/channeltag/grid?start=0&limit=200&all=1"
KODI_API = "http://127.0.0.1:8080/jsonrpc"
MAX_BYTES = 16 * 1024 * 1024
GROUP = re.compile(r'(?:^|\s)group-title="([^"]+)"')


def get_m3u_groups():
    with PLAYLIST.open("rb") as f:
        raw = f.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("PLAYLIST_TOO_LARGE")
    groups = []
    seen = set()
    for line in raw.decode("utf-8-sig").splitlines():
        if line.startswith("#EXTINF"):
            match = GROUP.search(line.partition(",")[0])
            if not match:
                raise ValueError("MISSING_GROUP")
            name = match.group(1).strip()
            if name not in seen:
                groups.append(name)
                seen.add(name)
    if not groups:
        raise ValueError("EMPTY_PLAYLIST_GROUPS")
    return groups


def read_json(request):
    with urllib.request.urlopen(request, timeout=10) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    return json.loads(raw)


def get_tvh_tags():
    result = read_json(urllib.request.Request(TVH_API))
    tags = result["entries"]
    if result["total"] != len(tags):
        raise ValueError("PARTIAL_TVH_TAG_GRID")
    return tags


def get_kodi_groups():
    body = json.dumps({
        "jsonrpc": "2.0", "id": 1,
        "method": "PVR.GetChannelGroups",
        "params": {"channeltype": "tv"}
    }).encode("utf-8")
    req = urllib.request.Request(
        KODI_API, data=body, method="POST",
        headers={"Content-Type": "application/json"}
    )
    result = read_json(req)
    if "error" in result:
        raise ValueError("KODI_JSONRPC_ERROR")
    value = result["result"]
    groups = value.get("channelgroups", [])
    limits = value.get("limits", {})
    if limits and limits.get("total") != len(groups):
        raise ValueError("PARTIAL_KODI_GROUPS")
    return groups


def inspect():
    desired = get_m3u_groups()
    tags = get_tvh_tags()
    tag_names = {t["name"] for t in tags}
    missing_tvh = [g for g in desired if g not in tag_names]
    extra_tvh = [t for t in tags if t["name"] not in set(desired)]
    print("M3U_GROUP_COUNT=" + str(len(desired)))
    print("TVH_TAG_COUNT=" + str(len(tags)))
    print("TVH_GROUPS_MISSING=" + str(len(missing_tvh)))
    print("TVH_EXTRA_TAGS=" + str(len(extra_tvh)))

    kodi = get_kodi_groups()
    # Kodi may include synthetic 'All channels' and non-IPTV groups.
    names = [g.get("label", "") for g in kodi]
    matched = [name for name in names if name in set(desired)]
    missing_kodi = [name for name in desired if name not in names]
    expected_relative = [name for name in desired if name in set(matched)]
    print("KODI_GROUP_COUNT=" + str(len(kodi)))
    print("KODI_M3U_GROUPS_PRESENT=" + str(len(matched)))
    print("KODI_M3U_GROUPS_MISSING=" + str(len(missing_kodi)))
    print("KODI_ORDER_MATCH=" + ("YES" if matched == expected_relative else "NO"))
    print("KODI_GROUPS_PRESENT_IN_ORDER:")
    for name in matched:
        print(" - " + name)
    print("READ_ONLY=YES")
    print("APPLY_AUTHORIZED=NO")


if __name__ == "__main__":
    try:
        inspect()
    except Exception as exc:
        print("RESULT=INCONCLUSIVE")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("READ_ONLY=YES")
        print("APPLY_AUTHORIZED=NO")
        sys.exit(2)
