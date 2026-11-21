#!/usr/bin/env python3
"""G3-R: inspect TVH automatic IPTV network without changing anything.

Only GET calls; never prints playlist URL, credentials, M3U content or
stream URLs. Intended for the CoreELEC master as a separate diagnostic.
"""
import json
import os
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9981/api/"
TARGET = "cce41e6f2d9b5d829d3af38159eea0a5"
PLAYLIST = Path("/storage/.user/playlist.m3u")
LIMIT = 2 * 1024 * 1024


def _request(endpoint, params):
    if endpoint not in ("mpegts/network/grid", "idnode/load"):
        raise ValueError("UNAPPROVED_ENDPOINT")
    req = urllib.request.Request(
        BASE + endpoint + "?" + urllib.parse.urlencode(params),
        method="GET", headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status != 200:
            raise ValueError("HTTP_NOT_OK")
        payload = response.read(LIMIT + 1)
    if len(payload) > LIMIT:
        raise ValueError("OVERSIZED_RESPONSE")
    result = json.loads(payload)
    if not isinstance(result, dict):
        raise ValueError("INVALID_RESPONSE")
    return result


def inspect():
    if not PLAYLIST.is_file() or PLAYLIST.is_symlink():
        raise ValueError("PLAYLIST_UNAVAILABLE")
    grid = _request("mpegts/network/grid", {"start": 0, "limit": 200, "all": 1})
    entries = grid.get("entries")
    if (not isinstance(entries, list) or type(grid.get("total")) is not int
            or grid["total"] != len(entries)):
        raise ValueError("INCOMPLETE_NETWORK_GRID")
    selected = [x for x in entries if isinstance(x, dict) and x.get("uuid") == TARGET]
    if len(selected) != 1:
        raise ValueError("TARGET_NETWORK_AMBIGUOUS")
    network = selected[0]
    response = _request("idnode/load", {"uuid": TARGET})
    nodes = response.get("entries")
    if not isinstance(nodes, list) or len(nodes) != 1:
        raise ValueError("NETWORK_IDNODE_NOT_UNIQUE")
    node = nodes[0]
    if node.get("uuid") != TARGET:
        raise ValueError("IDNODE_UUID_MISMATCH")
    # TVH builds differ in exposing properties under 'props'; do not infer
    # absent keys as default values.
    props = node.get("props")
    if not isinstance(props, list):
        raise ValueError("NETWORK_PROPERTIES_UNAVAILABLE")
    by_name = {}
    for prop in props:
        if not isinstance(prop, dict):
            continue
        key = prop.get("id")
        if isinstance(key, str):
            by_name[key] = prop.get("value")
    network_url = by_name.get("url", network.get("url"))
    if network_url is None:
        url_status = "UNKNOWN"
    else:
        url_status = ("EXPECTED_LOCAL_FILE" if
                      network_url == "file:///storage/.user/playlist.m3u"
                      else "UNEXPECTED_OR_CHANGED")
    period = by_name.get("refetch_period", network.get("refetch_period"))
    if type(period) is int and 1 <= period <= 1440:
        period_text = str(period)
    else:
        period_text = "UNKNOWN"
    print("=== G3-R TVH IPTV NETWORK / GET ONLY ===")
    print("TARGET_NETWORK_FOUND=YES")
    print("PLAYLIST_PATH_EXISTS=YES")
    print("SOURCE_URL_STATUS=" + url_status)
    print("REFETCH_PERIOD_MINUTES=" + period_text)
    print("TVH_NETWORKS=" + str(len(entries)))
    print("GET_ONLY=YES")
    print("TRIGGER_EXECUTED=NO")
    print("TVH_RESTART_EXECUTED=NO")
    print("KODI_SQLITE_TOUCHED=NO")
    print("TRIGGER_SUPPORTED_PROVEN=NO")
    return 0 if url_status == "EXPECTED_LOCAL_FILE" and period_text != "UNKNOWN" else 2


if __name__ == "__main__":
    try:
        sys.exit(inspect())
    except (Exception, KeyboardInterrupt) as err:
        print("G3R=BLOCKED")
        print("ERROR_TYPE=" + type(err).__name__)
        print("GET_ONLY=YES")
        print("TRIGGER_EXECUTED=NO")
        sys.exit(2)
