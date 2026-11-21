#!/usr/bin/env python3
"""G3-V offline acceptance of isolated TVH/Kodi add/remove observations.

Input is a JSON file produced by an ISOLATED test environment, not a request
to mutate the master. No network, no SQLite, no commands to start/restart TVH.
Rejects only-count evidence: requires unique channel IDs per system and
stable IDs for retained channels. No claim that M3U CUID is carried through.
"""
import argparse
import json
from pathlib import Path


class GateBlocked(ValueError):
    pass


def _indexed(rows, kind):
    if not isinstance(rows, list) or not rows:
        raise GateBlocked("INVALID_" + kind + "_INVENTORY")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise GateBlocked("INVALID_" + kind + "_ROW")
        identity, label = row.get("id"), row.get("name")
        if (not isinstance(identity, str) or not identity or
                not isinstance(label, str) or not label or
                identity in result):
            raise GateBlocked("INVALID_" + kind + "_IDENTITY")
        result[identity] = label
    return result


def evaluate(report):
    if not isinstance(report, dict) or report.get("schema") != 1:
        raise GateBlocked("INVALID_REPORT_SCHEMA")
    if report.get("lab_isolated") is not True:
        raise GateBlocked("ISOLATION_NOT_PROVEN")
    stages = report.get("stages")
    if not isinstance(stages, dict) or set(stages) != {"before", "added", "removed"}:
        raise GateBlocked("INVALID_STAGES")
    proof = {}
    for stage in ("before", "added", "removed"):
        state = stages[stage]
        if not isinstance(state, dict):
            raise GateBlocked("INVALID_STAGE")
        # A separately prepared fixture must be checked by the operator.
        # Re-fetch evidence must not be inferred from channel counts.
        if state.get("tvh_refetch_observed") is not True:
            raise GateBlocked("TVH_REFETCH_NOT_OBSERVED")
        proof[stage] = {
            "tvh": _indexed(state.get("tvh"), "TVH"),
            "kodi": _indexed(state.get("kodi"), "KODI"),
        }
    if any(len(proof[s][k]) != v for s, v in
           (("before", 2), ("added", 3), ("removed", 2))
           for k in ("tvh", "kodi")):
        raise GateBlocked("EXPECTED_DELTA_NOT_OBSERVED")
    for system in ("tvh", "kodi"):
        a, b, c = (proof[stage][system] for stage in
                   ("before", "added", "removed"))
        if not (set(a) < set(b) and c == a):
            raise GateBlocked(system.upper() + "_DELTA_NOT_CONVERGED")
        if any(b[identity] != name for identity, name in a.items()):
            raise GateBlocked(system.upper() + "_RETAINED_CHANNEL_CHANGED")
        newly_added = set(b) - set(a)
        if len(newly_added) != 1:
            raise GateBlocked(system.upper() + "_ADDED_ID_AMBIGUOUS")
    # No cross-system ID equivalence inferred. Operator must supply proof
    # that Kodi is attached only to the lab TVH and not to live IPTV.
    if report.get("kodi_connected_only_to_lab_tvh") is not True:
        raise GateBlocked("KODI_LAB_CONNECTION_NOT_PROVEN")
    if report.get("production_untouched") is not True:
        raise GateBlocked("PRODUCTION_UNTOUCHED_NOT_PROVEN")
    return {
        "lab_delta": "PASS",
        "tvh_add": "PASS", "tvh_remove": "PASS",
        "kodi_add": "PASS", "kodi_remove": "PASS",
        "retained_ids_stable": "PASS",
        "production_writes": "NO",
        "cuid_to_tvh_kodi_proven": "NO",
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("report", help="Local, isolated lab evidence JSON")
    args = parser.parse_args(argv)
    path = Path(args.report)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
        print("G3V=BLOCKED")
        print("REASON=REPORT_UNAVAILABLE")
        return 2
    try:
        with path.open("r", encoding="utf-8") as stream:
            result = evaluate(json.load(stream))
    except (GateBlocked, ValueError, OSError, UnicodeError) as exc:
        reason = str(exc) if type(exc) is GateBlocked else "INVALID_REPORT"
        known = {
            "INVALID_REPORT_SCHEMA", "ISOLATION_NOT_PROVEN", "INVALID_STAGES",
            "INVALID_STAGE", "TVH_REFETCH_NOT_OBSERVED",
            "INVALID_TVH_INVENTORY", "INVALID_KODI_INVENTORY",
            "INVALID_TVH_ROW", "INVALID_KODI_ROW",
            "INVALID_TVH_IDENTITY", "INVALID_KODI_IDENTITY",
            "EXPECTED_DELTA_NOT_OBSERVED", "TVH_DELTA_NOT_CONVERGED",
            "KODI_DELTA_NOT_CONVERGED", "TVH_RETAINED_CHANNEL_CHANGED",
            "KODI_RETAINED_CHANNEL_CHANGED", "TVH_ADDED_ID_AMBIGUOUS",
            "KODI_ADDED_ID_AMBIGUOUS",
            "KODI_LAB_CONNECTION_NOT_PROVEN",
            "PRODUCTION_UNTOUCHED_NOT_PROVEN",
        }
        print("G3V=BLOCKED")
        print("REASON=" + (reason if reason in known else "INVALID_REPORT"))
        return 2
    print("=== G3-V ISOLATED LAB DELTA GATE ===")
    for key, value in result.items():
        print(key.upper() + "=" + value)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
