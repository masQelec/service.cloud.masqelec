#!/usr/bin/env python3
"""G3-AC: read-only TVH/Kodi inventory observer with per-run identity baseline.

No PVR resets, Kodi SQL, HTSP writes, credentials or stream URLs.
"""
import argparse
import json
import time
import urllib.request

TVH = "http://127.0.0.1:19991/api/channel/grid?start=0&limit=100"
KODI = "http://127.0.0.1:8080/jsonrpc"
EXPECTED_NAMES = frozenset(("G3AB Alpha", "G3AB Beta"))


def get_tvh():
    with urllib.request.urlopen(TVH, timeout=8) as response:
        obj = json.load(response)
    rows = obj.get("entries")
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("INVALID_TVH_INVENTORY")
    return rows


def get_kodi():
    payload = json.dumps({"jsonrpc": "2.0", "method": "PVR.GetChannels",
                          "params": {"channelgroupid": "alltv"}, "id": 1}).encode()
    req = urllib.request.Request(KODI, data=payload,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=8) as response:
        obj = json.load(response)
    if "error" in obj:
        raise ValueError("KODI_JSONRPC_ERROR")
    rows = obj.get("result", {}).get("channels")
    if not isinstance(rows, list) or len(rows) > 100:
        raise ValueError("INVALID_KODI_INVENTORY")
    return rows


def identity_snapshot(tvh_rows, kodi_rows):
    """Only the controlled G3AB pair, with unique name and identifier validation."""
    if len(tvh_rows) != 2 or len(kodi_rows) != 2:
        raise ValueError("INVENTORY_NOT_TWO")
    t_names = [c.get("name") for c in tvh_rows]
    k_names = [c.get("label") for c in kodi_rows]
    if (not all(isinstance(n, str) and n.startswith("G3AB ") for n in t_names + k_names)
            or len(set(t_names)) != 2 or len(set(k_names)) != 2):
        raise ValueError("UNEXPECTED_OR_AMBIGUOUS_SOURCE")
    t_map = {c["name"]: c.get("uuid") for c in tvh_rows}
    k_map = {c["label"]: c.get("channelid") for c in kodi_rows}
    if (any(not isinstance(v, str) or not v for v in t_map.values())
            or len(set(t_map.values())) != 2
            or any(type(v) is not int or v <= 0 for v in k_map.values())
            or len(set(k_map.values())) != 2):
        raise ValueError("INVALID_OR_DUPLICATE_IDENTIFIERS")
    return t_map, k_map


def evaluate(tvh_rows, kodi_rows, baseline=None):
    """Compare inventories and identity maps. No CUID/HTSP event claims."""
    try:
        tvh_map, kodi_map = identity_snapshot(tvh_rows, kodi_rows)
    except (ValueError, KeyError, TypeError):
        return {"status": "BLOCKED_INVALID_INVENTORY", "tvh_count": len(tvh_rows),
                "kodi_count": len(kodi_rows), "names_match": False}
    names_match = set(tvh_map) == set(kodi_map)
    result = {
        "status": "OBSERVED_ONLY", "tvh_count": 2, "kodi_count": 2,
        "names_match": names_match,
        "tvh_names": sorted(tvh_map), "kodi_names": sorted(kodi_map),
        "tvh_uuids_by_name": dict(sorted(tvh_map.items())),
        "kodi_ids_by_name": dict(sorted(kodi_map.items())),
        "tvh_uuids_stable_since_sample1": None if baseline is None else tvh_map == baseline[0],
        "kodi_ids_stable_since_sample1": None if baseline is None else kodi_map == baseline[1],
        "htsp_event_seen": "NOT_MEASURED",
        "kodi_trigger_seen": "NOT_MEASURED",
        "cuid_mapping_proven": False, "sqlite_touched": False,
    }
    return result


def run(samples, interval):
    baseline = None
    for i in range(samples):
        try:
            tvh_rows = get_tvh()
            kodi_rows = get_kodi()
            result = evaluate(tvh_rows, kodi_rows, baseline)
            print("G3AC_SAMPLE=" + str(i + 1))
            for key, value in result.items():
                print(key.upper() + "=" + json.dumps(value, ensure_ascii=False))
            if result["status"] != "OBSERVED_ONLY":
                return 2
            current = identity_snapshot(tvh_rows, kodi_rows)
            if baseline is None:
                baseline = current
            elif (not result["tvh_uuids_stable_since_sample1"]
                  or not result["kodi_ids_stable_since_sample1"]):
                print("G3AC=IDENTITY_CHANGED_DURING_OBSERVATION")
                return 2
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            print("G3AC=BLOCKED_READ_ONLY_ERROR")
            print("ERROR_TYPE=" + type(error).__name__)
            return 2
        if i + 1 < samples:
            time.sleep(interval)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval", type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.samples <= 20 or not 0 <= args.interval <= 60:
        parser.error("bounded samples 1..20 and interval 0..60 required")
    raise SystemExit(run(args.samples, args.interval))
