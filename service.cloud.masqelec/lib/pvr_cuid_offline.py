"""G3-AA: fail-closed, offline M3U CUID identity comparison.

This reads two local files and reports aggregate changes, never URLs, CUID
values or channel names. It does not imply that TVH or Kodi honor CUID.
"""
from collections import Counter
from pathlib import Path
import re

MAX_BYTES = 8 * 1024 * 1024
MAX_CHANNELS = 20000
ATTR = re.compile(r"(?<![\w-])([\w-]+)\s*=\s*([\"'])(.*?)\2", re.UNICODE)


class Blocked(ValueError):
    pass


def _attribute(extinf, wanted):
    matches = [m.group(3) for m in ATTR.finditer(extinf)
               if m.group(1).casefold() == wanted.casefold()]
    if len(matches) != 1:
        raise Blocked("ATTRIBUTE_MISSING_OR_DUPLICATE")
    return matches[0].strip()


def parse(content):
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_BYTES:
        raise Blocked("INVALID_PLAYLIST")
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].strip() != "#EXTM3U":
        raise Blocked("MISSING_M3U_HEADER")
    result = {}
    pending = None
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            if pending is not None:
                raise Blocked("MISSING_STREAM_URL")
            cuid = _attribute(line, "CUID")
            if not cuid or len(cuid) > 128:
                raise Blocked("INVALID_CUID")
            if cuid in result:
                raise Blocked("DUPLICATE_CUID")
            name = _attribute(line, "tvg-name")
            group = _attribute(line, "group-title")
            if not name or not group:
                raise Blocked("INVALID_NAME_OR_GROUP")
            pending = (cuid, name, group)
        elif line.startswith("#"):
            continue
        else:
            if pending is None:
                raise Blocked("URL_WITHOUT_EXTINF")
            if not (line.startswith("http://") or line.startswith("https://")):
                raise Blocked("UNSUPPORTED_STREAM_URL")
            cuid, name, group = pending
            result[cuid] = {"name": name, "group": group, "url": line,
                            "position": len(result)}
            pending = None
            if len(result) > MAX_CHANNELS:
                raise Blocked("TOO_MANY_CHANNELS")
    if pending is not None:
        raise Blocked("MISSING_STREAM_URL")
    if not result:
        raise Blocked("EMPTY_PLAYLIST")
    return result


def compare(before, after):
    if not isinstance(before, dict) or not isinstance(after, dict) or not before or not after:
        raise Blocked("INVALID_SNAPSHOTS")
    old_ids, new_ids = set(before), set(after)
    stable = old_ids & new_ids
    old_names = Counter(item["name"] for item in before.values())
    new_names = Counter(item["name"] for item in after.values())
    return {
        "status": "OFFLINE_CUID_COMPARISON_ONLY",
        "before_channels": len(before),
        "after_channels": len(after),
        "retained_cuids": len(stable),
        "added_cuids": len(new_ids - old_ids),
        "removed_cuids": len(old_ids - new_ids),
        "renamed": sum(before[c]["name"] != after[c]["name"] for c in stable),
        "url_changed": sum(before[c]["url"] != after[c]["url"] for c in stable),
        "group_changed": sum(before[c]["group"] != after[c]["group"] for c in stable),
        "position_changed": sum(before[c]["position"] != after[c]["position"] for c in stable),
        "ambiguous_names_before": sum(v for v in old_names.values() if v > 1),
        "ambiguous_names_after": sum(v for v in new_names.values() if v > 1),
        "tvh_preserves_cuid_proven": False,
        "kodi_preserves_cuid_proven": False,
        "delete_authorized": False,
    }


def load(path):
    source = Path(path)
    if source.is_symlink() or not source.is_file() or source.stat().st_size > MAX_BYTES:
        raise Blocked("UNSAFE_OR_MISSING_PLAYLIST")
    try:
        return parse(source.read_text(encoding="utf-8"))
    except (UnicodeError, OSError):
        raise Blocked("INVALID_PLAYLIST_ENCODING") from None
