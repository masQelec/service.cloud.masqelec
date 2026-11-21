#!/usr/bin/env python3
"""G3-Z2: read-only TVH channel->service UUID reference resolution, isolated lab.

GET-only on hard-coded loopback G3-W. Does not display IDs, names, M3U URLs,
credentials or stream locations; never touches Kodi, master or SQLite.
"""
import json
import re
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:19981"
MAX_BYTES = 16 * 1024 * 1024
UUID_RE = re.compile(r"^[0-9a-fA-F]{32}$")


class Blocked(ValueError):
    pass


def evaluate(channels, services):
    if not isinstance(channels, dict) or not isinstance(services, dict):
        raise Blocked("INVALID_JSON_SHAPE")
    rows = channels.get("entries")
    total = channels.get("total")
    srv_rows = services.get("entries")
    if (type(total) is not int or not isinstance(rows, list)
            or not 0 < total <= 20000 or total != len(rows)
            or not isinstance(srv_rows, list) or not srv_rows):
        raise Blocked("INCOMPLETE_INVENTORY")

    service_ids = set()
    for row in srv_rows:
        if not isinstance(row, dict) or not UUID_RE.fullmatch(str(row.get("key", ""))):
            raise Blocked("INVALID_SERVICE_LIST_ID")
        ident = row["key"].lower()
        if ident in service_ids:
            raise Blocked("DUPLICATE_SERVICE_LIST_ID")
        service_ids.add(ident)

    channel_ids = set()
    referenced = []
    for row in rows:
        if not isinstance(row, dict) or not UUID_RE.fullmatch(str(row.get("uuid", ""))):
            raise Blocked("INVALID_CHANNEL_UUID")
        ident = row["uuid"].lower()
        if ident in channel_ids:
            raise Blocked("DUPLICATE_CHANNEL_UUID")
        channel_ids.add(ident)
        links = row.get("services")
        if not isinstance(links, list) or not links:
            raise Blocked("CHANNEL_WITHOUT_SERVICE")
        local = set()
        for ref in links:
            if not isinstance(ref, str) or not UUID_RE.fullmatch(ref):
                raise Blocked("INVALID_SERVICE_REFERENCE")
            ref = ref.lower()
            if ref in local:
                raise Blocked("DUPLICATE_SERVICE_REFERENCE")
            local.add(ref)
            referenced.append(ref)

    unresolved = set(referenced) - service_ids
    return {
        "channel_count": total,
        "available_service_count": len(service_ids),
        "service_reference_count": len(referenced),
        "unique_referenced_services": len(set(referenced)),
        "unresolved_references": len(unresolved),
        "tvh_channel_service_reference_proven": "YES" if not unresolved else "NO",
        "cuid_mapping_proven": "NO",
        "tvh_to_kodi_identity_proven": "NO",
        "deletion_authorized": "NO",
        "production_touched": "NO",
    }


def _fetch(path):
    req = urllib.request.Request(BASE + path, method="GET",
                                 headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status != 200:
                raise Blocked("TVH_HTTP_ERROR")
            raw = response.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise Blocked("TVH_AUTH_REQUIRED") from None
        raise Blocked("TVH_HTTP_ERROR") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        raise Blocked("TVH_UNREACHABLE") from None
    if len(raw) > MAX_BYTES:
        raise Blocked("RESPONSE_TOO_LARGE")
    try:
        result = json.loads(raw)
    except (ValueError, UnicodeError):
        raise Blocked("TVH_INVALID_JSON") from None
    return result


def run():
    try:
        channels = _fetch("/api/channel/grid?start=0&limit=20000")
        services = _fetch("/api/service/list?enum=1")
        outcome = evaluate(channels, services)
    except Blocked as exc:
        print("G3Z2=BLOCKED")
        print("REASON=" + str(exc))
        return 2
    if outcome["unresolved_references"]:
        print("G3Z2=BLOCKED")
        print("REASON=UNRESOLVED_SERVICE_REFERENCES")
        print("UNRESOLVED_REFERENCES=" + str(outcome["unresolved_references"]))
        return 2
    print("G3Z2=TVH_SERVICE_UUID_RELATION_PASS")
    for key, value in outcome.items():
        print(key.upper() + "=" + str(value))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception:
        print("G3Z2=BLOCKED")
        print("REASON=UNCLASSIFIED")
        sys.exit(2)
