"""G3-C: deterministic, read-only TVH channel-tag reconciliation planner.

No Tvheadend API writes, no Kodi/SQLite access, no filesystem tag changes.
The caller must obtain complete, consistent TVH inventories after M3U refetch.
"""
from collections import Counter
import re

_GROUP = re.compile(r'(?<![\w-])group-title\s*=\s*"([^"]*)"')


class PlanBlocked(ValueError):
    """Invalid or ambiguous snapshot: no actions may be applied."""


def m3u_groups(playlist):
    """Extract ordered, unique group-title values from an M3U text snapshot."""
    if not isinstance(playlist, str) or not playlist.lstrip("\ufeff").startswith("#EXTM3U"):
        raise PlanBlocked("INVALID_M3U_HEADER")
    result, seen, channel_count = [], set(), 0
    for line in playlist.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        channel_count += 1
        found = _GROUP.search(line)
        if not found or not found.group(1).strip():
            raise PlanBlocked("MISSING_GROUP_TITLE")
        name = found.group(1).strip()
        if name not in seen:
            seen.add(name)
            result.append(name)
    if channel_count < 1 or not result:
        raise PlanBlocked("EMPTY_M3U")
    return result, channel_count


def plan(playlist, tags_response, channels_response, owned_tag_uuids=()):
    """Return read-only action candidates; never authorize execution.

    owned_tag_uuids is an explicit persisted ownership registry, NOT inferred
    from empty tags, names, UUID format, or membership in a previous M3U.
    """
    groups, m3u_count = m3u_groups(playlist)
    if not isinstance(tags_response, dict) or not isinstance(channels_response, dict):
        raise PlanBlocked("INVALID_RESPONSE")
    tags, channels = tags_response.get("entries"), channels_response.get("entries")
    if not isinstance(tags, list) or not isinstance(channels, list):
        raise PlanBlocked("MISSING_ENTRIES")
    for source, entries in ((tags_response, tags), (channels_response, channels)):
        if (type(source.get("total")) is not int or
                source["total"] != len(entries)):
            raise PlanBlocked("INCOMPLETE_INVENTORY")
    if len(channels) != m3u_count:
        raise PlanBlocked("REFETCH_NOT_CONVERGED")
    if len(channels) < 1 or any(not isinstance(c, dict) for c in channels):
        raise PlanBlocked("INVALID_CHANNELS")
    if any(not isinstance(t, dict) for t in tags):
        raise PlanBlocked("INVALID_TAGS")
    names = [t.get("name") for t in tags]
    uuids = [t.get("uuid") for t in tags]
    if any(not isinstance(n, str) or not n.strip() for n in names):
        raise PlanBlocked("INVALID_TAG_NAMES")
    if any(not isinstance(u, str) or not u for u in uuids):
        raise PlanBlocked("INVALID_TAG_UUID")
    if len(set(uuids)) != len(uuids):
        raise PlanBlocked("DUPLICATE_TAG_UUID")
    if any(v > 1 for v in Counter(names).values()):
        raise PlanBlocked("AMBIGUOUS_TAG_NAMES")
    for ch in channels:
        if not isinstance(ch.get("tags"), list):
            raise PlanBlocked("MISSING_CHANNEL_TAG_LINKS")
        if any(not isinstance(u, str) for u in ch["tags"]):
            raise PlanBlocked("INVALID_CHANNEL_TAG_LINKS")
    known = set(uuids)
    referenced = {u for c in channels for u in c["tags"]}
    if not referenced <= known:
        raise PlanBlocked("UNKNOWN_CHANNEL_TAG_REFERENCE")
    if any(not c["tags"] for c in channels):
        raise PlanBlocked("UNTAGGED_CHANNELS")

    by_name = {t["name"]: t for t in tags}
    desired = set(groups)
    owned = set(owned_tag_uuids)
    if not owned <= known:
        raise PlanBlocked("STALE_OWNERSHIP_REGISTRY")
    create = [name for name in groups if name not in by_name]
    reorder = [
        {"uuid": by_name[name]["uuid"], "position": index}
        for index, name in enumerate(groups, 1)
        if name in by_name and by_name[name].get("index") != index
    ]
    unused = [t for t in tags if t["name"] not in desired and t["uuid"] not in referenced]
    # Existing empty categories are NOT adopted implicitly.
    delete_candidates = [
        t["uuid"] for t in unused
        if t["uuid"] in owned and t.get("internal") is False
    ]
    protected = [t["uuid"] for t in unused if t["uuid"] not in delete_candidates]
    return {
        "status": "DRY_RUN_ONLY",
        "m3u_channels": m3u_count,
        "tvh_channels": len(channels),
        "desired_groups": len(groups),
        "existing_groups": len(tags),
        "create_names": create,
        "reorder_candidates": reorder,
        "delete_owned_empty_candidates": delete_candidates,
        "preserved_unowned_or_internal_empty": protected,
        "apply_authorized": False,
    }
