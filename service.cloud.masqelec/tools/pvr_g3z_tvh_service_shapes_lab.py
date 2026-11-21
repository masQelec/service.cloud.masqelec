#!/usr/bin/env python3
"""G3-Z: inspect TVH channel->service references in isolated G3-W, read-only.

Reports only shapes, types and counts. Never prints service IDs, URLs,
channel names, stream endpoints or credentials. No Kodi/SQLite access.
"""
import json
import sys
import urllib.request
import urllib.error

URL = "http://127.0.0.1:19981/api/channel/grid?start=0&limit=20000"
MAX_BYTES = 16 * 1024 * 1024


class Blocked(ValueError):
    pass


def inspect(document):
    if not isinstance(document, dict):
        raise Blocked("INVALID_RESPONSE")
    entries = document.get("entries")
    total = document.get("total")
    if (type(total) is not int or not isinstance(entries, list)
            or not 0 < total <= 20000 or len(entries) != total):
        raise Blocked("PARTIAL_INVENTORY")

    shapes = {}
    refs = 0
    empty = 0
    for row in entries:
        if not isinstance(row, dict) or not isinstance(row.get("uuid"), str) or not row["uuid"]:
            raise Blocked("INVALID_CHANNEL")
        services = row.get("services")
        if not isinstance(services, list):
            raise Blocked("SERVICES_NOT_LIST")
        if not services:
            empty += 1
        for service in services:
            refs += 1
            kind = type(service).__name__
            shapes[kind] = shapes.get(kind, 0) + 1
            if isinstance(service, dict):
                key_names = tuple(sorted(service.keys()))
                safe_key_names = tuple(k for k in key_names if isinstance(k, str) and
                                       k.isidentifier() and len(k) <= 48)
                if safe_key_names != key_names:
                    raise Blocked("UNSAFE_SERVICE_KEYS")
                marker = "object_fields:" + ",".join(safe_key_names)
                shapes[marker] = shapes.get(marker, 0) + 1
    return {
        "status": "TVH_SERVICE_REFERENCE_SHAPES_ONLY",
        "channels": total,
        "channels_with_no_services": empty,
        "service_references": refs,
        "reference_shapes": dict(sorted(shapes.items())),
        "cuid_mapping_proven": "NO",
        "tvh_to_kodi_identity_proven": "NO",
        "deletion_authorized": "NO",
        "master_touched": "NO",
    }


def run():
    try:
        req = urllib.request.Request(URL, method="GET",
                                     headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status != 200:
                raise Blocked("TVH_HTTP_ERROR")
            raw = response.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise Blocked("RESPONSE_TOO_LARGE")
        result = inspect(json.loads(raw))
    except urllib.error.HTTPError as exc:
        reason = "TVH_AUTH_REQUIRED" if exc.code in (401, 403) else "TVH_HTTP_ERROR"
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        reason = "TVH_UNREACHABLE"
    except Blocked as exc:
        reason = str(exc)
    except (ValueError, UnicodeError, TypeError):
        reason = "INVALID_JSON"
    else:
        print("G3Z=SHAPES_ONLY")
        for key, value in result.items():
            print(key.upper() + "=" + json.dumps(value, ensure_ascii=False, sort_keys=True))
        return 0
    print("G3Z=BLOCKED")
    print("REASON=" + reason)
    return 2


if __name__ == "__main__":
    sys.exit(run())
