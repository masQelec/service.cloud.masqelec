#!/usr/bin/env python3
"""G3-I: read-only gate for *one* formerly used TVH channel tag.

No API mutation, no Kodi SQLite, no secrets printed. PRECHECK != approval
for deletion: exact ownership and rollback are separate requirements.
"""
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

TVH = "http://127.0.0.1:9981/api/"
KODI = "http://127.0.0.1:8080/jsonrpc"
PLAYLIST = Path("/storage/.user/playlist.m3u")
TARGET_UUID = "3e6be21d508c4effb8de6195294739b9"
TARGET_NAME = "ES - NBA"
MAX_BYTES = 16 * 1024 * 1024
GROUP = re.compile(r'(?:^|\s)group-title="([^"]+)"')


def _json(req):
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("RESPONSE_TOO_LARGE")
    return json.loads(raw)


def _grid(endpoint, limit):
    if endpoint not in ("channeltag/grid", "channel/grid"):
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    req = urllib.request.Request(
        TVH + endpoint + "?start=0&limit=" + str(limit) + "&all=1"
    )
    data = _json(req)
    if (not isinstance(data, dict)
            or not isinstance(data.get("entries"), list)
            or type(data.get("total")) is not int
            or data["total"] != len(data["entries"])):
        raise ValueError("INCOMPLETE_GRID")
    return data["entries"]


def _m3u_groups():
    with PLAYLIST.open("rb") as handle:
        payload = handle.read(MAX_BYTES + 1)
    if len(payload) > MAX_BYTES:
        raise ValueError("PLAYLIST_TOO_LARGE")
    lines = payload.decode("utf-8-sig").splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        raise ValueError("INVALID_PLAYLIST")
    names, count = set(), 0
    for line in lines:
        if not line.startswith("#EXTINF"):
            continue
        count += 1
        matched = GROUP.search(line.partition(",")[0])
        if not matched or not matched.group(1).strip():
            raise ValueError("GROUP_MISSING")
        names.add(matched.group(1).strip())
    if not count:
        raise ValueError("EMPTY_PLAYLIST")
    return names, count


def _kodi_groups():
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "PVR.GetChannelGroups",
        "params": {"channeltype": "tv"},
    }).encode()
    req = urllib.request.Request(KODI, data=body, method="POST", headers={
        "Content-Type": "application/json"
    })
    response = _json(req)
    if not isinstance(response, dict) or "error" in response:
        raise ValueError("KODI_JSONRPC_ERROR")
    data = response.get("result")
    if not isinstance(data, dict) or not isinstance(data.get("channelgroups"), list):
        raise ValueError("KODI_INVALID_GROUPS")
    rows = data["channelgroups"]
    limits = data.get("limits")
    if isinstance(limits, dict) and limits.get("total") != len(rows):
        raise ValueError("KODI_PARTIAL_GROUPS")
    return rows


def _tag_definition_readable():
    params = urllib.parse.urlencode({"uuid": TARGET_UUID})
    result = _json(urllib.request.Request(TVH + "idnode/load?" + params))
    if not isinstance(result, dict) or not result:
        raise ValueError("TAG_DEFINITION_UNAVAILABLE")
    # Do not print or persist raw metadata; different TVH versions vary.
    return True


def inspect():
    groups, m3u_count = _m3u_groups()
    tags = _grid("channeltag/grid", 200)
    channels = _grid("channel/grid", 20000)
    kodi = _kodi_groups()

    matches = [row for row in tags if row.get("uuid") == TARGET_UUID]
    tag_names = [row.get("name") for row in tags]
    name_count = tag_names.count(TARGET_NAME)
    target = matches[0] if len(matches) == 1 else None
    occupied = sum(
        1 for channel in channels
        if isinstance(channel.get("tags"), list)
        and TARGET_UUID in channel["tags"]
    )
    incomplete_channels = sum(
        1 for channel in channels if not isinstance(channel.get("tags"), list)
    )
    kodi_count = sum(row.get("label") == TARGET_NAME for row in kodi)

    print("=== G3-I PRECHECK / NO WRITES ===")
    print("M3U_CHANNELS=" + str(m3u_count))
    print("TVH_CHANNELS=" + str(len(channels)))
    print("TVH_TAGS=" + str(len(tags)))
    print("TARGET_PRESENT_IN_M3U=" + str(TARGET_NAME in groups).upper())
    print("TARGET_TAG_MATCHES=" + str(len(matches)))
    print("TARGET_NAME_MATCHES=" + str(name_count))
    print("TARGET_TVH_LINKED_CHANNELS=" + str(occupied))
    print("TARGET_KODI_GROUP_MATCHES=" + str(kodi_count))
    print("CHANNEL_ROWS_WITHOUT_TAGS_LIST=" + str(incomplete_channels))

    prelim = (target is not None and target.get("name") == TARGET_NAME
              and target.get("internal") is False
              and name_count == 1 and TARGET_NAME not in groups
              and occupied == 0 and kodi_count == 1
              and incomplete_channels == 0 and m3u_count == len(channels))
    if prelim:
        _tag_definition_readable()
    print("PRECHECK=" + ("PASS" if prelim else "BLOCKED"))
    print("OWNERSHIP_VERIFIED=NO")
    print("ROLLBACK_VERIFIED=NO")
    print("DELETE_AUTHORIZED=NO")
    return 0 if prelim else 2


if __name__ == "__main__":
    try:
        sys.exit(inspect())
    except (Exception, KeyboardInterrupt) as exc:
        print("RESULT=INCONCLUSIVE")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("DELETE_AUTHORIZED=NO")
        sys.exit(2)
