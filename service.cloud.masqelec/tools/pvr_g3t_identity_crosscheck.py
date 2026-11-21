#!/usr/bin/env python3
"""G3-T: read-only per-channel M3U vs TVH name/group crosscheck.

This proves *descriptive* linkage only, NOT channel CUID technical identity,
a refetch event, or Kodi convergence. No API writes or output of names/URLs.
"""
from collections import Counter
import json
from pathlib import Path
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

M3U = Path("/storage/.user/playlist.m3u")
API = "http://127.0.0.1:9981/api/"
MAX_M3U = 16 * 1024 * 1024
MAX_GRID = 24 * 1024 * 1024
LIMITS = {"channeltag/grid": 200, "channel/grid": 20000}
GROUP = re.compile(r'(?<![\w-])group-title\s*=\s*"([^"]+)"')


class Blocked(ValueError):
    pass


def norm(value):
    if not isinstance(value, str):
        raise Blocked("INVALID_NAME")
    return unicodedata.normalize("NFC", value).strip()


def parse_m3u(text):
    if not isinstance(text, str) or not text.lstrip("\ufeff").startswith("#EXTM3U"):
        raise Blocked("INVALID_M3U")
    result = []
    for line in text.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        found = GROUP.search(line)
        if not found or "," not in line:
            raise Blocked("INVALID_EXTINF")
        group = norm(found.group(1))
        name = norm(line.split(",", 1)[1])
        if not group or not name:
            raise Blocked("EMPTY_NAME_OR_GROUP")
        result.append((name, group))
    if not result:
        raise Blocked("EMPTY_M3U")
    return Counter(result)


def _grid(endpoint):
    if endpoint not in LIMITS:
        raise Blocked("UNAPPROVED_ENDPOINT")
    query = urllib.parse.urlencode({
        "start": 0, "limit": LIMITS[endpoint], "all": 1})
    request = urllib.request.Request(
        API + endpoint + "?" + query, method="GET",
        headers={"Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            raise Blocked("HTTP_NOT_OK")
        raw = response.read(MAX_GRID + 1)
    if len(raw) > MAX_GRID:
        raise Blocked("GRID_TOO_LARGE")
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise Blocked("INVALID_GRID")
    entries = result.get("entries")
    if (not isinstance(entries, list)
            or type(result.get("total")) is not int
            or result["total"] != len(entries)
            or len(entries) > LIMITS[endpoint]):
        raise Blocked("INCOMPLETE_GRID")
    return entries


def compare(m3u_pairs, tags, channels):
    if not isinstance(m3u_pairs, Counter) or not m3u_pairs:
        raise Blocked("INVALID_INPUT")
    tag_names = {}
    for tag in tags:
        if not isinstance(tag, dict):
            raise Blocked("INVALID_TAG")
        uuid = tag.get("uuid")
        if not isinstance(uuid, str) or not uuid or uuid in tag_names:
            raise Blocked("DUPLICATE_TAG_UUID")
        tag_names[uuid] = norm(tag.get("name"))
    counts = Counter()
    duplicate_channel_uuids = set()
    for ch in channels:
        if not isinstance(ch, dict):
            raise Blocked("INVALID_CHANNEL")
        uuid = ch.get("uuid")
        if not isinstance(uuid, str) or not uuid or uuid in duplicate_channel_uuids:
            raise Blocked("INVALID_CHANNEL_UUID")
        duplicate_channel_uuids.add(uuid)
        name, memberships = norm(ch.get("name")), ch.get("tags")
        if not name or not isinstance(memberships, list) or not memberships:
            raise Blocked("INVALID_CHANNEL_LINKS")
        if any(t not in tag_names for t in memberships):
            raise Blocked("UNKNOWN_TAG_REFERENCE")
        for group in set(tag_names[t] for t in memberships):
            counts[(name, group)] += 1
    # Compare only groups present in M3U; extra legacy groups must not
    # create spurious mismatches in the desired-group comparison.
    desired_groups = {g for _, g in m3u_pairs}
    tvh_desired = Counter({
        pair: number for pair, number in counts.items()
        if pair[1] in desired_groups
    })
    matching = sum(min(n, tvh_desired.get(pair, 0))
                   for pair, n in m3u_pairs.items())
    extra = sum(max(0, n - m3u_pairs.get(pair, 0))
                for pair, n in tvh_desired.items())
    missing = sum(max(0, n - tvh_desired.get(pair, 0))
                  for pair, n in m3u_pairs.items())
    ambiguous = sum(n for n in m3u_pairs.values() if n > 1)
    # A channel may have multiple tags and therefore multiple pairs.
    multitag = sum(len(c.get("tags", [])) > 1 for c in channels)
    return {
        "m3u_channels": sum(m3u_pairs.values()),
        "tvh_channels": len(channels),
        "m3u_distinct_name_group_pairs": len(m3u_pairs),
        "exact_name_group_matches": matching,
        "missing_name_group_pairs": missing,
        "extra_tvh_name_group_pairs": extra,
        "m3u_ambiguous_duplicate_entries": ambiguous,
        "tvh_multitag_channels": multitag,
        "match_gate": "PASS" if missing == 0 and extra == 0
                      and matching == len(channels)
                      and len(channels) == sum(m3u_pairs.values())
                      else "INCOMPLETE",
        "identity_disambiguation": "NOT_PROVEN" if ambiguous else "DESCRIPTIVELY_UNIQUE",
        "cuid_mapping_proven": "NO",
        "refetch_event_proven": "NO",
        "kodi_convergence_proven": "NO",
        "api_write_executed": "NO",
    }


def inspect():
    if M3U.is_symlink() or not M3U.is_file():
        raise Blocked("PLAYLIST_UNAVAILABLE")
    with M3U.open("rb") as stream:
        raw = stream.read(MAX_M3U + 1)
    if len(raw) > MAX_M3U:
        raise Blocked("PLAYLIST_TOO_LARGE")
    try:
        m3u = parse_m3u(raw.decode("utf-8-sig"))
    except UnicodeError as exc:
        raise Blocked("INVALID_M3U_ENCODING") from exc
    tags = _grid("channeltag/grid")
    channels = _grid("channel/grid")
    result = compare(m3u, tags, channels)
    print("=== G3-T PER-CHANNEL DESCRIPTIVE CROSSCHECK ===")
    for key, value in result.items():
        print(key.upper() + "=" + str(value))
    return 0 if result["match_gate"] == "PASS" else 2


if __name__ == "__main__":
    try:
        sys.exit(inspect())
    except (Exception, KeyboardInterrupt) as error:
        allowed = {
            "INVALID_NAME", "INVALID_M3U", "INVALID_EXTINF",
            "EMPTY_NAME_OR_GROUP", "EMPTY_M3U", "UNAPPROVED_ENDPOINT",
            "HTTP_NOT_OK", "GRID_TOO_LARGE", "INVALID_GRID",
            "INCOMPLETE_GRID", "INVALID_INPUT", "INVALID_TAG",
            "DUPLICATE_TAG_UUID", "INVALID_CHANNEL", "INVALID_CHANNEL_UUID",
            "INVALID_CHANNEL_LINKS", "UNKNOWN_TAG_REFERENCE",
            "PLAYLIST_UNAVAILABLE", "PLAYLIST_TOO_LARGE",
            "INVALID_M3U_ENCODING",
        }
        message = str(error) if type(error) is Blocked else ""
        print("G3T=BLOCKED")
        print("REASON=" + (message if message in allowed else "UNCLASSIFIED"))
        print("WRITE_EXECUTED=NO")
        sys.exit(2)
