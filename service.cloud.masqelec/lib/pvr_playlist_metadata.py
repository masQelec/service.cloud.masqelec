"""Strict, side-effect-free M3U metadata inventory for PVR migration planning.

Never log or return stream URLs, credentials, or the original EXTINF text.
CUID is stable *within a generation*; comparing two generations requires
explicit operator-verified adoption mappings.
"""
from dataclasses import dataclass
import re

MAX_BYTES = 8 * 1024 * 1024
MAX_CHANNELS = 20000
_ATTR = re.compile(r'([A-Za-z][A-Za-z0-9_-]*)="([^"]*)"')


class PlaylistInvalid(ValueError):
    pass


@dataclass(frozen=True)
class Channel:
    cuid: str
    name: str
    group: str
    number: int
    epg_id: str


def parse_metadata(raw: bytes):
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise PlaylistInvalid("invalid playlist byte size")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError as exc:
        raise PlaylistInvalid("invalid encoding") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines or lines[0] != "#EXTM3U":
        raise PlaylistInvalid("missing M3U header")
    if (len(lines)-1) % 2:
        raise PlaylistInvalid("missing metadata or stream entry")
    if (len(lines)-1)//2 > MAX_CHANNELS:
        raise PlaylistInvalid("too many channels")
    result = []
    used_cuid, used_numbers = set(), set()
    for i in range(1, len(lines), 2):
        info, stream = lines[i], lines[i+1]
        if not info.startswith("#EXTINF:") or "," not in info:
            raise PlaylistInvalid("invalid EXTINF record")
        if not stream or stream.startswith("#"):
            raise PlaylistInvalid("invalid stream entry")
        attrs = dict(_ATTR.findall(info.partition(",")[0]))
        cuid = attrs.get("CUID", "")
        first = attrs.get("tvh-chnum", "")
        second = attrs.get("tvg-chno", "")
        if not cuid.isdecimal() or int(cuid) < 1 or cuid in used_cuid:
            raise PlaylistInvalid("missing or duplicate CUID")
        if not first.isdecimal() or int(first) < 1 or first != second:
            raise PlaylistInvalid("inconsistent channel number")
        number = int(first)
        if number in used_numbers:
            raise PlaylistInvalid("duplicate number")
        name = info.partition(",")[2].strip()
        group = attrs.get("group-title", "")
        if not name or not group:
            raise PlaylistInvalid("missing channel or group")
        used_cuid.add(cuid)
        used_numbers.add(number)
        result.append(Channel(cuid=cuid, name=name, group=group,
                              number=number, epg_id=attrs.get("tvg-id", "")))
    if not result:
        raise PlaylistInvalid("empty playlist")
    return tuple(result)


def diff_same_generation(old, new, *, generation_verified=False):
    """Never interpret changed CUID membership as removals without a gate."""
    if not generation_verified:
        raise PlaylistInvalid("identity generation not verified")
    old_ids = {c.cuid: c for c in old}
    new_ids = {c.cuid: c for c in new}
    if len(old_ids) != len(old) or len(new_ids) != len(new):
        raise PlaylistInvalid("duplicate CUID in inventory")
    common = old_ids.keys() & new_ids.keys()
    return {
        "added": sorted(new_ids.keys() - old_ids.keys(), key=int),
        "removed_candidates": sorted(old_ids.keys() - new_ids.keys(), key=int),
        "changed": sorted([x for x in common if old_ids[x] != new_ids[x]], key=int),
        "unchanged_count": sum(old_ids[x] == new_ids[x] for x in common),
        "destructive_operations_authorized": False,
    }
