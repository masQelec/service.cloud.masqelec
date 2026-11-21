#!/usr/bin/env python3
"""G3-S: two read-only TVH snapshots across IPTV LOCAL refresh interval.

Does not prove that TVH re-fetched unchanged content. No POST, no file write,
no channel names, URLs, credentials or identifiers printed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import urllib.request

M3U = Path("/storage/.user/playlist.m3u")
API = "http://127.0.0.1:9981/api/"
MAX_M3U = 16 * 1024 * 1024
MAX_JSON = 24 * 1024 * 1024
ENDPOINTS = {"channel/grid": 20000, "channeltag/grid": 200}


class GateBlocked(ValueError):
    pass


def _read_m3u():
    if M3U.is_symlink() or not M3U.is_file():
        raise GateBlocked("PLAYLIST_NOT_REGULAR")
    with M3U.open("rb") as f:
        raw = f.read(MAX_M3U + 1)
    if len(raw) > MAX_M3U:
        raise GateBlocked("PLAYLIST_TOO_LARGE")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise GateBlocked("PLAYLIST_BAD_ENCODING") from exc
    if not text.startswith("#EXTM3U"):
        raise GateBlocked("PLAYLIST_BAD_HEADER")
    groups = set()
    import re
    for line in text.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        match = re.search(r'(?<![\w-])group-title\s*=\s*"([^"]+)"', line)
        if match is None or not match.group(1).strip():
            raise GateBlocked("PLAYLIST_GROUP_UNAVAILABLE")
        groups.add(match.group(1).strip())
    count = sum(line.startswith("#EXTINF") for line in text.splitlines())
    if count == 0 or not groups:
        raise GateBlocked("PLAYLIST_EMPTY")
    return hashlib.sha256(raw).hexdigest(), count, groups


def _grid(endpoint):
    if endpoint not in ENDPOINTS:
        raise GateBlocked("ENDPOINT_NOT_ALLOWED")
    params = urllib.parse.urlencode({"start": 0, "limit": ENDPOINTS[endpoint], "all": 1})
    req = urllib.request.Request(API + endpoint + "?" + params,
                                 method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        if r.status != 200:
            raise GateBlocked("TVH_HTTP_NOT_OK")
        data = r.read(MAX_JSON + 1)
    if len(data) > MAX_JSON:
        raise GateBlocked("TVH_GRID_TOO_LARGE")
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise GateBlocked("TVH_GRID_INVALID")
    entries = payload.get("entries")
    if (not isinstance(entries, list) or type(payload.get("total")) is not int
            or payload["total"] != len(entries)
            or len(entries) > ENDPOINTS[endpoint]):
        raise GateBlocked("TVH_GRID_INCOMPLETE")
    return entries


def capture():
    before_hash, m3u_count, group_names = _read_m3u()
    tags = _grid("channeltag/grid")
    channels = _grid("channel/grid")
    after_hash, _, _ = _read_m3u()
    if before_hash != after_hash:
        raise GateBlocked("PLAYLIST_CHANGED_DURING_READ")
    if len(channels) != m3u_count:
        raise GateBlocked("TVH_CHANNEL_COUNT_MISMATCH")
    by_uuid = {}
    names = set()
    for tag in tags:
        if not isinstance(tag, dict):
            raise GateBlocked("TVH_TAG_INVALID")
        uuid, name = tag.get("uuid"), tag.get("name")
        if (not isinstance(uuid, str) or not uuid
                or not isinstance(name, str) or not name
                or uuid in by_uuid or name in names):
            raise GateBlocked("TVH_TAG_DUPLICATE_OR_INVALID")
        by_uuid[uuid] = name
        names.add(name)
    if not group_names <= names:
        raise GateBlocked("M3U_GROUP_NOT_IN_TVH")
    links = {}
    for channel in channels:
        if not isinstance(channel, dict):
            raise GateBlocked("TVH_CHANNEL_INVALID")
        uuid, assigned = channel.get("uuid"), channel.get("tags")
        if (not isinstance(uuid, str) or not uuid or uuid in links
                or not isinstance(assigned, list) or not assigned
                or any(not isinstance(t, str) or t not in by_uuid for t in assigned)):
            raise GateBlocked("TVH_CHANNEL_LINK_INVALID")
        links[uuid] = tuple(sorted(set(assigned)))
    referenced = {tag for assigned in links.values() for tag in assigned}
    groups_unlinked = sorted(group_names - {by_uuid[t] for t in referenced})
    return {
        "playlist_hash": before_hash, "m3u_count": m3u_count,
        "m3u_group_count": len(group_names),
        "tvh_tag_count": len(tags),
        "tvh_channel_count": len(channels),
        "tag_identity": by_uuid, "channel_links": links,
        "desired_groups_without_channel_links": len(groups_unlinked),
        "protected_or_other_tags": len(names - group_names),
    }


def compare(a, b):
    if a["playlist_hash"] != b["playlist_hash"]:
        raise GateBlocked("PLAYLIST_CHANGED_BETWEEN_SNAPSHOTS")
    if a["m3u_count"] != b["m3u_count"]:
        raise GateBlocked("PLAYLIST_CHANNEL_COUNT_CHANGED")
    if a["tag_identity"] != b["tag_identity"]:
        raise GateBlocked("TVH_TAG_INVENTORY_CHANGED")
    if a["channel_links"] != b["channel_links"]:
        raise GateBlocked("TVH_CHANNEL_MEMBERSHIP_CHANGED")
    if a["desired_groups_without_channel_links"] or b["desired_groups_without_channel_links"]:
        raise GateBlocked("M3U_GROUP_WITHOUT_CHANNEL_LINKS")
    return {
        "status": "STABLE_TWO_SNAPSHOTS",
        "m3u_channels": b["m3u_count"],
        "tvh_channels": b["tvh_channel_count"],
        "m3u_groups": b["m3u_group_count"],
        "tvh_tags": b["tvh_tag_count"],
        "unmatched_historic_tags": b["protected_or_other_tags"],
    }


def run(delay=75, read=capture, sleep=time.sleep):
    if type(delay) is not int or delay < 65 or delay > 180:
        raise GateBlocked("INVALID_DELAY")
    a = read()
    sleep(delay)
    b = read()
    return compare(a, b)


def main():
    parser = argparse.ArgumentParser(description="Read-only TVH interval observation")
    parser.add_argument("--delay", type=int, default=75)
    args = parser.parse_args()
    try:
        result = run(delay=args.delay)
    except (Exception, KeyboardInterrupt) as exc:
        codes = {
            "PLAYLIST_NOT_REGULAR", "PLAYLIST_TOO_LARGE", "PLAYLIST_BAD_ENCODING",
            "PLAYLIST_BAD_HEADER", "PLAYLIST_GROUP_UNAVAILABLE",
            "PLAYLIST_EMPTY", "ENDPOINT_NOT_ALLOWED", "TVH_HTTP_NOT_OK",
            "TVH_GRID_TOO_LARGE", "TVH_GRID_INVALID", "TVH_GRID_INCOMPLETE",
            "PLAYLIST_CHANGED_DURING_READ", "TVH_CHANNEL_COUNT_MISMATCH",
            "TVH_TAG_INVALID", "TVH_TAG_DUPLICATE_OR_INVALID",
            "M3U_GROUP_NOT_IN_TVH", "TVH_CHANNEL_INVALID",
            "TVH_CHANNEL_LINK_INVALID", "PLAYLIST_CHANGED_BETWEEN_SNAPSHOTS",
            "PLAYLIST_CHANNEL_COUNT_CHANGED", "TVH_TAG_INVENTORY_CHANGED",
            "TVH_CHANNEL_MEMBERSHIP_CHANGED", "M3U_GROUP_WITHOUT_CHANNEL_LINKS",
            "INVALID_DELAY",
        }
        message = str(exc) if type(exc) is GateBlocked else ""
        print("G3S=BLOCKED")
        print("REASON=" + (message if message in codes else "UNCLASSIFIED"))
        print("ERROR_TYPE=" + type(exc).__name__)
        print("GET_ONLY=YES")
        print("WRITE_EXECUTED=NO")
        return 2
    print("=== G3-S TVH TWO-SNAPSHOT OBSERVATION ===")
    for key, value in result.items():
        print(key.upper() + "=" + str(value))
    print("INTERVAL_SECONDS=" + str(args.delay))
    print("GET_ONLY=YES")
    print("WRITE_EXECUTED=NO")
    print("REFETCH_EVENT_PROVEN=NO")
    print("CHANNEL_CUID_MAPPING_PROVEN=NO")
    print("KODI_CONVERGENCE_PROVEN=NO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
