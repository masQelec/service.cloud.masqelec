#!/usr/bin/env python3
"""G3-AD: observe an Alpha-only rename without mutating TVH, Kodi, PVR, or SQL.

Start from G3AB Alpha/Beta before executing 'prepare.py rename' in another shell.
Identity is tracked by baseline TVH UUID and Kodi JSON-RPC channelid, never by label.
"""
import argparse
import json
import time

import pvr_g3ac_observe as data

ORIGINAL = "G3AB Alpha"
RENAMED = "G3AB Alpha Renamed"
BETA = "G3AB Beta"


def read_state(tvh_rows, kodi_rows, baseline=None):
    """Return bounded sanitized state; throw on unexpected channels or ambiguity."""
    if len(tvh_rows) != 2 or len(kodi_rows) != 2:
        raise ValueError("INVENTORY_NOT_TWO")
    if any(not isinstance(r, dict) for r in tvh_rows + kodi_rows):
        raise ValueError("INVALID_ROWS")
    tvh_names = [r.get("name") for r in tvh_rows]
    kodi_names = [r.get("label") for r in kodi_rows]
    allowed = {ORIGINAL, RENAMED, BETA}
    if (len(set(tvh_names)) != 2 or len(set(kodi_names)) != 2
            or set(tvh_names) - allowed or set(kodi_names) - allowed
            or BETA not in tvh_names or BETA not in kodi_names):
        raise ValueError("UNEXPECTED_NAME_OR_AMBIGUITY")
    tvh_by_name = {r["name"]: r for r in tvh_rows}
    kodi_by_name = {r["label"]: r for r in kodi_rows}
    if (any(not isinstance(r.get("uuid"), str) or not r["uuid"] for r in tvh_rows)
            or len({r["uuid"] for r in tvh_rows}) != 2
            or any(type(r.get("channelid")) is not int or r["channelid"] <= 0
                   for r in kodi_rows)
            or len({r["channelid"] for r in kodi_rows}) != 2):
        raise ValueError("INVALID_IDENTIFIERS")

    tvh_a = next(r for r in tvh_rows if r["name"] in (ORIGINAL, RENAMED))
    kodi_a = next(r for r in kodi_rows if r["label"] in (ORIGINAL, RENAMED))
    tvh_b = tvh_by_name[BETA]
    kodi_b = kodi_by_name[BETA]
    current = {
        "tvh_alpha_name": tvh_a["name"],
        "tvh_alpha_uuid": tvh_a["uuid"],
        "tvh_beta_uuid": tvh_b["uuid"],
        "kodi_alpha_name": kodi_a["label"],
        "kodi_alpha_id": kodi_a["channelid"],
        "kodi_beta_id": kodi_b["channelid"],
        "tvh_alpha_renamed": tvh_a["name"] == RENAMED,
        "kodi_alpha_renamed": kodi_a["label"] == RENAMED,
        "names_match": set(tvh_by_name) == set(kodi_by_name),
    }
    if baseline is None:
        if current["tvh_alpha_renamed"] or current["kodi_alpha_renamed"]:
            raise ValueError("RENAME_ALREADY_APPLIED_BEFORE_BASELINE")
        current["tvh_uuid_stable"] = None
        current["kodi_id_stable"] = None
    else:
        current["tvh_uuid_stable"] = (
            tvh_a["uuid"] == baseline["tvh_alpha_uuid"]
            and tvh_b["uuid"] == baseline["tvh_beta_uuid"])
        current["kodi_id_stable"] = (
            kodi_a["channelid"] == baseline["kodi_alpha_id"]
            and kodi_b["channelid"] == baseline["kodi_beta_id"])
    return current


def run(samples, interval):
    baseline = None
    previous = None
    observed_tvh_rename = False
    observed_kodi_rename = False
    for number in range(1, samples + 1):
        try:
            state = read_state(data.get_tvh(), data.get_kodi(), baseline)
            if baseline is None:
                baseline = state.copy()
            observed_tvh_rename |= state["tvh_alpha_renamed"]
            observed_kodi_rename |= state["kodi_alpha_renamed"]
            # Print the first observation, every changed state, and the final sample.
            changed = state != previous
            if number == 1 or changed or number == samples:
                print("G3AD_SAMPLE=" + str(number), flush=True)
                for key, value in state.items():
                    print(key.upper() + "=" + json.dumps(value, ensure_ascii=False), flush=True)
            if state["tvh_uuid_stable"] is False or state["kodi_id_stable"] is False:
                print("G3AD=IDENTITY_CHANGED_ABORT", flush=True)
                return 2
            previous = state
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print("G3AD=READ_ONLY_DIAGNOSTIC_BLOCKED", flush=True)
            print("ERROR_TYPE=" + type(exc).__name__, flush=True)
            return 2
        if number < samples:
            time.sleep(interval)
    if not observed_tvh_rename:
        print("G3AD=TVH_RENAME_NOT_OBSERVED", flush=True)
        return 3
    if not observed_kodi_rename:
        print("G3AD=TVH_RENAMED_KODI_NOT_OBSERVED", flush=True)
        return 4
    print("G3AD=BOTH_RENAMES_OBSERVED_NO_HTSP_TRACE", flush=True)
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=40)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    if not 2 <= args.samples <= 90 or not 1 <= args.interval <= 20:
        parser.error("samples 2..90 and interval 1..20 required")
    raise SystemExit(run(args.samples, args.interval))
