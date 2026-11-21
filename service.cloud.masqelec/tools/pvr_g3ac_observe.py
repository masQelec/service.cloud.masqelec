#!/usr/bin/env python3
"""G3-AC: read-only observation of TVH and Kodi channel metadata convergence.

No PVR resets, no Kodi SQL access, no credentials/URLs printed.
"""
import argparse
import json
import time
import urllib.request

TVH = "http://127.0.0.1:19991/api/channel/grid?start=0&limit=100"
KODI = "http://127.0.0.1:8080/jsonrpc"
EXPECTED = {
    "G3AB Alpha": ("185e5bdda6aafa6aa1aad2bb94ee703a", 2),
    "G3AB Beta": ("f08f75aa26b58386630d4b225adbb34f", 1),
}


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


def evaluate(tvh_rows, kodi_rows):
    """Compare only synthetic G3AB inventories, no CUID→backend mapping claim."""
    if len(tvh_rows) != 2 or len(kodi_rows) != 2:
        return {"status": "BLOCKED_INVENTORY_NOT_TWO",
                "tvh_count": len(tvh_rows), "kodi_count": len(kodi_rows),
                "names_match": False, "id_preserved": False}
    t_names = sorted(str(c.get("name", "")) for c in tvh_rows)
    k_names = sorted(str(c.get("label", "")) for c in kodi_rows)
    if not all(n.startswith("G3AB ") for n in t_names + k_names):
        return {"status": "BLOCKED_UNEXPECTED_SOURCE",
                "tvh_count": 2, "kodi_count": 2,
                "names_match": False, "id_preserved": False}
    # This records only the known synthetic Kodi baseline identities.
    k_by_id = {c.get("channelid"): c for c in kodi_rows}
    ids_stable = (len(k_by_id) == 2 and
                  1 in k_by_id and 2 in k_by_id and
                  "Beta" in str(k_by_id[1].get("label", "")) and
                  "Alpha" in str(k_by_id[2].get("label", "")))
    return {"status": "OBSERVED_ONLY", "tvh_count": 2, "kodi_count": 2,
            "names_match": t_names == k_names, "id_preserved": ids_stable,
            "tvh_names": t_names, "kodi_names": k_names,
            "htsp_event_seen": "NOT_MEASURED",
            "kodi_trigger_seen": "NOT_MEASURED",
            "cuid_mapping_proven": False, "sqlite_touched": False}


def run(samples, interval):
    for i in range(samples):
        try:
            result = evaluate(get_tvh(), get_kodi())
            print("G3AC_SAMPLE=" + str(i + 1))
            for key, value in result.items():
                print(key.upper() + "=" + json.dumps(value, ensure_ascii=False))
            if result["status"] != "OBSERVED_ONLY":
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
