#!/usr/bin/env python3
"""G3-Y: inspect exposed identity *fields* without leaking URLs or credentials.

Read-only network requests only: TVH /api/channel/grid and Kodi PVR.GetChannels.
No SQLite access; no TVH/Kodi mutation. This deliberately does NOT infer CUID
from names, numbering, icon URL or matching index.
"""
import argparse
import json
import sys
import urllib.request
import urllib.error
import socket

MAX_REPLY = 16 * 1024 * 1024
MAX_CHANNELS = 20000
TVH_FIELDS = ("uuid", "name", "number", "services", "bouquet", "tags")
KODI_FIELDS = ("channelid", "label", "channelnumber", "subchannelnumber", "uniqueid", "clientid")


class Blocked(ValueError):
    pass


def _fetch(request, source):
    """Fail closed, with non-sensitive failure categories per endpoint."""
    if source not in ("TVH", "KODI"):
        raise Blocked("INVALID_SOURCE")
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if response.status != 200:
                raise Blocked(source + "_HTTP_ERROR")
            content = response.read(MAX_REPLY + 1)
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if code in (401, 403):
            raise Blocked(source + "_AUTH_REQUIRED") from None
        if code == 404:
            raise Blocked(source + "_ENDPOINT_NOT_FOUND") from None
        raise Blocked(source + "_HTTP_ERROR") from None
    except (urllib.error.URLError, socket.timeout, TimeoutError,
            ConnectionError, OSError):
        raise Blocked(source + "_UNREACHABLE") from None
    if len(content) > MAX_REPLY:
        raise Blocked(source + "_RESPONSE_TOO_LARGE")
    try:
        value = json.loads(content)
    except (ValueError, UnicodeDecodeError):
        raise Blocked(source + "_INVALID_JSON") from None
    if not isinstance(value, dict):
        raise Blocked(source + "_INVALID_RESPONSE")
    return value


def _rows(document, key):
    rows = document.get(key)
    total = document.get("total") if key == "entries" else (document.get("limits") or {}).get("total")
    if not isinstance(rows, list) or type(total) is not int or not 0 < total <= MAX_CHANNELS or len(rows) != total:
        raise Blocked("PARTIAL_INVENTORY")
    if any(not isinstance(row, dict) for row in rows):
        raise Blocked("INVALID_INVENTORY")
    return rows


def _summary(tvh_rows, kodi_rows):
    """Only describe field presence, never map identities across products."""
    if not tvh_rows or not kodi_rows:
        raise Blocked("EMPTY_INVENTORY")
    return {
        "tvh_count": len(tvh_rows),
        "kodi_count": len(kodi_rows),
        "tvh_fields_present_all": sorted(set.intersection(*(set(row) for row in tvh_rows))),
        "kodi_fields_present_all": sorted(set.intersection(*(set(row) for row in kodi_rows))),
        "tvh_identity_field_types": {
            field: sorted({type(row[field]).__name__ for row in tvh_rows if field in row})
            for field in TVH_FIELDS if any(field in row for row in tvh_rows)
        },
        "kodi_identity_field_types": {
            field: sorted({type(row[field]).__name__ for row in kodi_rows if field in row})
            for field in KODI_FIELDS if any(field in row for row in kodi_rows)
        },
        "cuid_to_tvh_uuid_proven": "NO",
        "tvh_uuid_to_kodi_channelid_proven": "NO",
        "identity_deletion_authorized": "NO",
        "sqlite_touched": "NO",
    }


def probe(tvh_url, kodi_url):
    # Only the controlled lab loopback endpoints are accepted.
    if tvh_url != "http://127.0.0.1:19981" or kodi_url != "http://127.0.0.1:8080":
        raise Blocked("UNAPPROVED_ENDPOINT")
    tvh = _fetch(urllib.request.Request(
        tvh_url + "/api/channel/grid?start=0&limit=20000",
        method="GET", headers={"Accept": "application/json"}), "TVH")
    rpc = {"jsonrpc": "2.0", "id": 1, "method": "PVR.GetChannels",
           "params": {"channelgroupid": "alltv",
                      "properties": ["channelnumber", "subchannelnumber"],
                      "limits": {"start": 0, "end": 20000}}}
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    kodi = _fetch(urllib.request.Request(
        kodi_url + "/jsonrpc", data=json.dumps(rpc).encode(),
        headers=headers, method="POST"), "KODI")
    if "error" in kodi or not isinstance(kodi.get("result"), dict):
        raise Blocked("KODI_RPC_ERROR")
    return _summary(_rows(tvh, "entries"), _rows(kodi["result"], "channels"))


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--tvh", default="http://127.0.0.1:19981")
    parser.add_argument("--kodi", default="http://127.0.0.1:8080")
    opts = parser.parse_args(argv)
    try:
        result = probe(opts.tvh, opts.kodi)
    except Exception as exc:
        reason = str(exc) if type(exc) is Blocked else "API_UNAVAILABLE"
        print("G3Y=BLOCKED")
        print("REASON=" + reason)
        return 2
    print("G3Y=FIELD_INVENTORY_ONLY")
    for key, value in result.items():
        print(key.upper() + "=" + json.dumps(value, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
