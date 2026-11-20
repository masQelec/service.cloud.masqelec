"""G3-E: read-only, conservative M3U versus Tvheadend channel-group audit.

Name matches are diagnostic only, not proofs of CUID or stream identity.
No API writes, channel changes, or action authorization.
"""
from collections import Counter
import re

_ATTR_GROUP = re.compile(r'(?:^|\s)group-title\s*=\s*"([^"]*)"')


def audit(playlist, tags_grid, channel_grid):
    """Report exact-name group mismatches, fail closed on incomplete data.

    Every channel must have a unique exact name in both inventories for
    name-based association checks. Does not infer a technical identifier.
    """
    if not isinstance(playlist, str) or not playlist.lstrip("\ufeff").startswith("#EXTM3U"):
        return {"status": "BLOCKED", "reason": "INVALID_M3U", "apply_authorized": False}
    if not isinstance(tags_grid, dict) or not isinstance(channel_grid, dict):
        return {"status": "BLOCKED", "reason": "INVALID_GRID", "apply_authorized": False}
    tags, channels = tags_grid.get("entries"), channel_grid.get("entries")
    if not isinstance(tags, list) or not isinstance(channels, list):
        return {"status": "BLOCKED", "reason": "MISSING_ENTRIES", "apply_authorized": False}
    if any(type(grid.get("total")) is not int or grid["total"] != len(entries)
           for grid, entries in ((tags_grid, tags), (channel_grid, channels))):
        return {"status": "BLOCKED", "reason": "INCOMPLETE_GRID", "apply_authorized": False}

    source = []
    for line in playlist.splitlines():
        if not line.startswith("#EXTINF"):
            continue
        # EXTINF attributes precede the first comma; no private URLs are parsed.
        header, separator, display_name = line.partition(",")
        group_match = _ATTR_GROUP.search(header)
        if not separator or not display_name.strip() or not group_match or not group_match.group(1).strip():
            return {"status": "BLOCKED", "reason": "INVALID_EXTINF", "apply_authorized": False}
        source.append((display_name.strip(), group_match.group(1).strip()))
    if not source or len(source) != len(channels):
        return {"status": "DEFERRED", "reason": "COUNT_NOT_CONVERGED",
                "m3u_count": len(source), "tvh_count": len(channels), "apply_authorized": False}

    if any(not isinstance(t, dict) or not isinstance(t.get("uuid"), str)
           or not isinstance(t.get("name"), str) for t in tags):
        return {"status": "BLOCKED", "reason": "INVALID_TAGS", "apply_authorized": False}
    tag_ids = [t["uuid"] for t in tags]
    tag_names = [t["name"] for t in tags]
    if len(tag_ids) != len(set(tag_ids)) or len(tag_names) != len(set(tag_names)):
        return {"status": "BLOCKED", "reason": "AMBIGUOUS_TAGS", "apply_authorized": False}
    tag_by_uuid = {t["uuid"]: t["name"] for t in tags}

    if any(not isinstance(c, dict) or not isinstance(c.get("name"), str)
           or not isinstance(c.get("uuid"), str) or not isinstance(c.get("tags"), list)
           for c in channels):
        return {"status": "BLOCKED", "reason": "INVALID_CHANNELS", "apply_authorized": False}
    channel_uuids = [c["uuid"] for c in channels]
    if len(channel_uuids) != len(set(channel_uuids)):
        return {"status": "BLOCKED", "reason": "DUPLICATE_CHANNEL_UUID", "apply_authorized": False}
    if any(not isinstance(u, str) or u not in tag_by_uuid
           for c in channels for u in c["tags"]):
        return {"status": "BLOCKED", "reason": "UNKNOWN_CHANNEL_TAG", "apply_authorized": False}

    source_names = [name for name, _ in source]
    tvh_names = [c["name"] for c in channels]
    source_counts = Counter(source_names)
    tvh_counts = Counter(tvh_names)
    duplicated_source = sorted(name for name, count in source_counts.items() if count > 1)
    duplicated_tvh = sorted(name for name, count in tvh_counts.items() if count > 1)
    # Do not print names in bulk; report counts and small samples only.
    matched = set(source_counts) & set(tvh_counts)
    only_unique = {
        name for name in matched
        if source_counts[name] == 1 and tvh_counts[name] == 1
    }
    desired = dict(source)
    tvh_by_name = {c["name"]: c for c in channels if c["name"] in only_unique}
    mismatches = []
    for name in sorted(only_unique):
        actual = {tag_by_uuid[u] for u in tvh_by_name[name]["tags"]}
        if actual != {desired[name]}:
            mismatches.append({"channel_name": name, "expected": desired[name],
                               "actual_groups": sorted(actual)})
    unresolved = len(source) - len(only_unique)
    return {
        "status": "DIAGNOSTIC_ONLY" if not unresolved else "INCONCLUSIVE",
        "reason": "NAME_NOT_TECHNICAL_IDENTITY" if not unresolved else "AMBIGUOUS_OR_DIFFERENT_NAMES",
        "m3u_channels": len(source),
        "tvh_channels": len(channels),
        "exact_unique_name_pairs": len(only_unique),
        "unresolved_m3u_channels": unresolved,
        "duplicate_names_in_m3u": len(duplicated_source),
        "duplicate_names_in_tvh": len(duplicated_tvh),
        "group_mismatch_count": len(mismatches),
        "group_mismatch_samples": mismatches[:10],
        "apply_authorized": False,
    }
