#!/usr/bin/env python3
"""Read-only Kodi/PVR native diagnostics: Kodi TV channels versus TVH.

Never POST to TVH; Kodi JSON-RPC uses POST for read-only PVR.GetChannelGroups
and PVR.GetChannels requests. No SQLite access or channel names printed.
"""
import json
import sys
import urllib.request
import urllib.parse
from collections import Counter

TVH_API = "http://127.0.0.1:9981/api/channel/grid?start=0&limit=20000&all=1"
KODI_RPC = "http://127.0.0.1:8080/jsonrpc"
MAX_REPLY = 24 * 1024 * 1024


class Blocked(ValueError):
    pass


def _safe_json(request):
    with urllib.request.urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise Blocked("HTTP_NOT_OK")
        raw = response.read(MAX_REPLY + 1)
    if len(raw) > MAX_REPLY:
        raise Blocked("RESPONSE_TOO_LARGE")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise Blocked("INVALID_RESPONSE")
    return obj


def kodi(method, params):
    if method not in ("PVR.GetChannelGroups", "PVR.GetChannels"):
        raise Blocked("UNSUPPORTED_KODI_METHOD")
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                       "params": params}).encode("utf-8")
    req = urllib.request.Request(
        KODI_RPC, data=body, method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"})
    obj = _safe_json(req)
    if "error" in obj or not isinstance(obj.get("result"), dict):
        raise Blocked("KODI_RPC_ERROR")
    return obj["result"]


def tvh_channels():
    req = urllib.request.Request(TVH_API, method="GET",
                                 headers={"Accept": "application/json"})
    obj = _safe_json(req)
    rows = obj.get("entries")
    if not isinstance(rows, list) or type(obj.get("total")) is not int or len(rows) != obj["total"]:
        raise Blocked("TVH_INCOMPLETE_GRID")
    if any(not isinstance(x, dict) for x in rows):
        raise Blocked("TVH_INVALID_CHANNEL")
    return rows


def kodi_all_tv():
    groups = kodi("PVR.GetChannelGroups", {"channeltype": "tv"}).get("channelgroups")
    if not isinstance(groups, list):
        raise Blocked("KODI_GROUPS_UNAVAILABLE")
    # Kodi uses the special group identifier "alltv" for all TV channels.
    candidates = [g for g in groups if isinstance(g, dict)
                  and g.get("channelgroupid") == "alltv"]
    if len(candidates) != 1:
        raise Blocked("KODI_ALLTV_NOT_UNAMBIGUOUS")
    result = kodi("PVR.GetChannels", {
        "channelgroupid": candidates[0]["channelgroupid"],
        "properties": ["channelnumber", "subchannelnumber"],
        "limits": {"start": 0, "end": 20000},
    })
    rows = result.get("channels")
    limits = result.get("limits")
    if not isinstance(rows, list) or not isinstance(limits, dict):
        raise Blocked("KODI_CHANNELS_UNAVAILABLE")
    if (type(limits.get("total")) is not int or
            len(rows) != limits["total"] or len(rows) > 20000):
        raise Blocked("KODI_CHANNELS_PARTIAL")
    return rows


def _names(rows, key):
    result = Counter()
    for item in rows:
        if not isinstance(item, dict):
            raise Blocked("INVALID_CHANNEL")
        name = item.get(key)
        if not isinstance(name, str) or not name.strip():
            raise Blocked("CHANNEL_NAME_UNAVAILABLE")
        result[name.strip()] += 1
    return result


def summarize(tvh_rows, kodi_rows):
    a = _names(tvh_rows, "name")
    b = _names(kodi_rows, "label")
    common = sum(min(n, b.get(name, 0)) for name, n in a.items())
    result = {
        "tvh_channels": sum(a.values()),
        "kodi_channels": sum(b.values()),
        "matching_names_multiset": common,
        "kodi_unmatched_names": sum(max(0, n - a.get(name, 0)) for name, n in b.items()),
        "tvh_missing_in_kodi_names": sum(max(0, n - b.get(name, 0)) for name, n in a.items()),
        "ambiguous_tvh_names": sum(n for n in a.values() if n > 1),
        "ambiguous_kodi_names": sum(n for n in b.values() if n > 1),
        "native_orphan_removal_proven": "NO",
        "cuid_mapping_proven": "NO",
        "sqlite_touched": "NO",
        "tvh_mutation": "NO",
    }
    result["status"] = ("DESCRIPTIVE_MATCH" if
                        result["kodi_unmatched_names"] == 0 and
                        result["tvh_missing_in_kodi_names"] == 0 else
                        "DESCRIPTIVE_MISMATCH")
    return result


def run():
    tvh = tvh_channels()
    kodi_rows = kodi_all_tv()
    result = summarize(tvh, kodi_rows)
    print("=== KODI PVR READ-ONLY INVENTORY ===")
    for name, value in result.items():
        print(name.upper() + "=" + str(value))
    return 0 if result["status"] == "DESCRIPTIVE_MATCH" else 2


if __name__ == "__main__":
    try:
        sys.exit(run())
    except (Exception, KeyboardInterrupt) as exc:
        allow = {
            "HTTP_NOT_OK", "RESPONSE_TOO_LARGE", "INVALID_RESPONSE",
            "UNSUPPORTED_KODI_METHOD", "KODI_RPC_ERROR",
            "TVH_INCOMPLETE_GRID", "TVH_INVALID_CHANNEL",
            "KODI_GROUPS_UNAVAILABLE", "KODI_ALLTV_NOT_UNAMBIGUOUS",
            "KODI_CHANNELS_UNAVAILABLE", "KODI_CHANNELS_PARTIAL",
            "INVALID_CHANNEL", "CHANNEL_NAME_UNAVAILABLE",
        }
        reason = str(exc) if type(exc) is Blocked else ""
        print("KODI_NATIVE_READONLY=BLOCKED")
        print("REASON=" + (reason if reason in allow else "UNCLASSIFIED"))
        print("SQLITE_TOUCHED=NO")
        print("TVH_MUTATION=NO")
        sys.exit(2)
