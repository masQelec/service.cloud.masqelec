"""G2: read-only comparator for Kodi PVR vs Tvheadend inventories.

No network, no SQLite writes, no name-based deletion. Caller must supply a
verified crosswalk of TVH UUID -> (Kodi client ID, Kodi unique ID).
"""
from dataclasses import dataclass
from typing import Iterable


class InventoryError(ValueError):
    pass


@dataclass(frozen=True)
class TVHChannel:
    uuid: str
    number: int
    groups: tuple[str, ...] = ()


@dataclass(frozen=True)
class KodiChannel:
    client_id: int
    unique_id: int
    number: int
    groups: tuple[str, ...] = ()


def _unique_map(items: Iterable, key, source: str):
    result = {}
    for item in items:
        item_key = key(item)
        if item_key in result:
            raise InventoryError("duplicate identity in " + source)
        result[item_key] = item
    return result


def compare_inventories(tvh_channels, kodi_channels, crosswalk=None):
    """Return a plan, never an execution command.

    Without an externally validated identity crosswalk, all differences are
    ambiguous and deletion is blocked. Partial mappings also block deletion.
    """
    tvh = _unique_map(tvh_channels, lambda x: x.uuid, "TVH")
    kodi = _unique_map(
        kodi_channels, lambda x: (x.client_id, x.unique_id), "Kodi"
    )
    if any(not x.uuid or x.number < 1 for x in tvh.values()):
        raise InventoryError("invalid TVH identity or number")
    if any(x.client_id < 0 or x.unique_id < 0 or x.number < 1 for x in kodi.values()):
        raise InventoryError("invalid Kodi identity or number")
    base = {
        "status": "BLOCKED_UNVERIFIED_CROSSWALK",
        "tvh_count": len(tvh),
        "kodi_count": len(kodi),
        "orphan_candidates": [],
        "missing_candidates": [],
        "number_mismatches": [],
        "group_mismatches": [],
        "destructive_operations_authorized": False,
    }
    if not crosswalk:
        return base
    if set(crosswalk) != set(tvh) or len(set(crosswalk.values())) != len(crosswalk):
        return dict(base, status="BLOCKED_INCOMPLETE_CROSSWALK")
    mapped = set(crosswalk.values())
    all_kodi = set(kodi)
    for uuid, identity in crosswalk.items():
        if not isinstance(identity, tuple) or len(identity) != 2:
            raise InventoryError("invalid crosswalk identity")
        source = tvh[uuid]
        target = kodi.get(identity)
        if target is None:
            base["missing_candidates"].append(uuid)
            continue
        if source.number != target.number:
            base["number_mismatches"].append(uuid)
        if set(source.groups) != set(target.groups):
            base["group_mismatches"].append(uuid)
    base["orphan_candidates"] = sorted(all_kodi - mapped)
    base["status"] = (
        "UNCHANGED" if not any(base[k] for k in (
            "orphan_candidates", "missing_candidates", "number_mismatches",
            "group_mismatches"
        )) else "DIFFERENT"
    )
    return base
