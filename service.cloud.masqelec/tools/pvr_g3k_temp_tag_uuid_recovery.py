#!/usr/bin/env python3
"""G3-K controlled TVH API experiment on a disposable, empty channel tag only.

Creates a uniquely named tag, deletes it, attempts to re-create with the
original UUID in channeltag/create conf, then cleans any disposable tag.
Never deletes or edits pre-existing tags. Not an historical-tag rollback.
"""
import json
import sys
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:9981/api/"
LIMIT = 250
MAX_RESPONSE = 4 * 1024 * 1024
HISTORIC_UUID = "3e6be21d508c4effb8de6195294739b9"


def api(path, params=None, post=False):
    if (path, post) not in {
        ("channeltag/grid", False),
        ("channel/grid", False),
        ("channeltag/create", True),
        ("idnode/delete", True),
    }:
        raise ValueError("ENDPOINT_NOT_ALLOWED")
    params = params or {}
    url = BASE + path
    if not post:
        url += "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(params).encode("utf-8") if post else None
    req = urllib.request.Request(
        url, data=body, method="POST" if post else "GET",
        headers={"Accept": "application/json", "User-Agent": "masQelec-G3K-lab"},
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        if response.status != 200:
            raise ValueError("TVH_HTTP_STATUS")
        raw = response.read(MAX_RESPONSE + 1)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("TVH_RESPONSE_LIMIT")
    if not raw:
        return {}
    return json.loads(raw)


def grid(path, limit):
    response = api(path, {"start": 0, "limit": limit, "all": 1})
    if (not isinstance(response, dict)
            or not isinstance(response.get("entries"), list)
            or type(response.get("total")) is not int
            or response["total"] != len(response["entries"])):
        raise ValueError("INCOMPLETE_INVENTORY")
    return response["entries"]


def disposable_tags(name, original):
    """Only own fresh tag names; never accept an existing UUID as ours."""
    found = [tag for tag in grid("channeltag/grid", LIMIT)
             if tag.get("name") == name]
    if any(t.get("uuid") in original or t.get("uuid") == HISTORIC_UUID
           for t in found):
        raise ValueError("TEMP_COLLIDES_WITH_PREEXISTING")
    return found


def safe_delete(tag, name, original):
    """Delete only an unoccupied disposable tag, after re-reading TVH."""
    tag_id = tag.get("uuid")
    if (not isinstance(tag_id, str) or not tag_id or
            tag_id in original or tag_id == HISTORIC_UUID or
            tag.get("name") != name or tag.get("internal") is not False):
        raise ValueError("UNSAFE_DISPOSABLE_IDENTITY")
    current = disposable_tags(name, original)
    if len(current) != 1 or current[0].get("uuid") != tag_id:
        raise ValueError("DISPOSABLE_NOT_UNIQUE")
    channels = grid("channel/grid", 20000)
    if any(not isinstance(row.get("tags"), list) for row in channels):
        raise ValueError("INVALID_CHANNEL_TAGS")
    if any(tag_id in row["tags"] for row in channels):
        raise ValueError("DISPOSABLE_HAS_CHANNELS")
    api("idnode/delete", {"uuid": tag_id}, post=True)


def create(name, requested_uuid=None):
    conf = {"name": name, "enabled": True, "internal": False, "private": False}
    if requested_uuid:
        conf["uuid"] = requested_uuid
    api("channeltag/create", {"conf": json.dumps(conf)}, post=True)


def experiment():
    name = "MASQELEC_G3K_" + uuid.uuid4().hex
    original = {tag["uuid"] for tag in grid("channeltag/grid", LIMIT)}
    if len(original) != 32 or HISTORIC_UUID not in original:
        raise ValueError("UNEXPECTED_BASELINE")
    channels = grid("channel/grid", 20000)
    if len(channels) != 720:
        raise ValueError("UNEXPECTED_CHANNEL_COUNT")
    stage = "NOT_STARTED"
    requested = None
    try:
        if disposable_tags(name, original):
            raise ValueError("TEMP_NAME_COLLISION")
        create(name)
        items = disposable_tags(name, original)
        if len(items) != 1:
            raise ValueError("TEMP_CREATE_NOT_UNIQUE")
        requested = items[0].get("uuid")
        if not isinstance(requested, str) or not requested:
            raise ValueError("TEMP_MISSING_UUID")
        stage = "TEMP_CREATED"
        safe_delete(items[0], name, original)
        if disposable_tags(name, original):
            raise ValueError("TEMP_DELETE_NOT_CONFIRMED")
        stage = "TEMP_DELETED"
        # The API may ignore an explicit UUID. This experiment detects it.
        create(name, requested_uuid=requested)
        items = disposable_tags(name, original)
        if len(items) != 1:
            raise ValueError("TEMP_RECREATE_NOT_UNIQUE")
        preserved = items[0].get("uuid") == requested
        stage = "SAME_UUID" if preserved else "NEW_UUID"
        print("=== G3-K TEMPORARY TAG UUID RECOVERY ===")
        print("CREATE_DELETE=PASS")
        print("UUID_RECREATED_SAME=" + ("YES" if preserved else "NO"))
    finally:
        try:
            remaining = disposable_tags(name, original)
            # Only delete if a single unambiguous disposable exists.
            for item in remaining:
                if len(remaining) != 1:
                    raise ValueError("MULTIPLE_DISPOSABLE_TAGS")
                safe_delete(item, name, original)
            after = {t["uuid"] for t in grid("channeltag/grid", LIMIT)}
            print("INVENTORY_RESTORED=" + ("PASS" if after == original else "FAIL"))
        except Exception as exc:
            print("CLEANUP=REVIEW_REQUIRED")
            print("CLEANUP_ERROR_TYPE=" + type(exc).__name__)
            raise
    print("STAGE=" + stage)
    print("HISTORIC_TAG_TOUCHED=NO")
    print("HISTORIC_DELETE_AUTHORIZED=NO")
    # UUID recovery via create is a diagnostic, not proof of full restoration.
    print("FULL_CONFIGURATION_RESTORE_PROVEN=NO")
    return 0 if stage == "SAME_UUID" else 2


if __name__ == "__main__":
    try:
        sys.exit(experiment())
    except (Exception, KeyboardInterrupt) as exc:
        print("G3K=BLOCKED")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("HISTORIC_DELETE_AUTHORIZED=NO")
        sys.exit(2)
