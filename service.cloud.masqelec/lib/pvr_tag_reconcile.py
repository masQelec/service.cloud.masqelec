"""Safe, incremental TVH channel-tag reconciler (development-only).

A cycle performs at most ONE API mutation; callers inject read_snapshot() and
post(action, params). It deliberately does not rewrite Kodi SQLite, TVH tag
files, reorder tags or trigger a TVH/Kodi restart.

Ownership is an EXTERNAL, durable UUID registry. The caller MUST persist a
newly created UUID before allowing any future deletion. Existing tags are not
adopted from name or M3U history. This module never authorizes deletion by
itself: allow_delete is an explicit operator-side gate.
"""
import json

from .pvr_tag_plan import plan, PlanBlocked


class ReconcileBlocked(PlanBlocked):
    pass


def _snapshot(read_snapshot):
    response = read_snapshot()
    if not isinstance(response, (tuple, list)) or len(response) != 2:
        raise ReconcileBlocked("INVALID_SNAPSHOT")
    tags, channels = response
    return tags, channels


def _by_name(tags, name):
    return [t for t in tags["entries"] if t["name"] == name]


def _assert_identity(before, after, added, removed=()):
    old = {t["uuid"] for t in before["entries"]}
    new = {t["uuid"] for t in after["entries"]}
    if new - old != set(added) or old - new != set(removed):
        raise ReconcileBlocked("UNEXPECTED_TAG_INVENTORY_CHANGE")


def reconcile_once(playlist, read_snapshot, post, owned_uuids=(),
                   allow_delete=False):
    """Revalidate snapshots, then create missing tags, or delete owned empties.

    Returns a diagnostic dict; the caller must durably persist returned
    owned_tag_uuids on a successful CREATE before enabling any DELETE.
    Errors after a write are surfaced, never hidden as success.
    """
    tags, channels = _snapshot(read_snapshot)
    proposal = plan(playlist, tags, channels, owned_uuids)
    initial = {t["uuid"] for t in tags["entries"]}
    desired = set(owned_uuids)
    # Independently re-read the same complete snapshot immediately before
    # any write; refuse if the inventories drifted.
    new_tags, new_channels = _snapshot(read_snapshot)
    if tags != new_tags or channels != new_channels:
        raise ReconcileBlocked("INVENTORY_CHANGED")
    if proposal["create_names"]:
        name = proposal["create_names"][0]
        result = post("channeltag/create", {
            "conf": json.dumps({"name": name, "enabled": True,
                                "internal": False, "private": False})
        })
        if result is False:
            raise ReconcileBlocked("CREATE_FAILED")
        final_tags, final_channels = _snapshot(read_snapshot)
        # Do not rely on a new UUID from POST; prove it from TVH inventory.
        final_plan = plan(playlist, final_tags, final_channels, ())
        matches = _by_name(final_tags, name)
        if len(matches) != 1 or matches[0].get("internal") is not False:
            raise ReconcileBlocked("CREATE_NOT_CONFIRMED")
        created = matches[0]["uuid"]
        _assert_identity(tags, final_tags, {created})
        if created in initial or name in final_plan["create_names"]:
            raise ReconcileBlocked("CREATE_NOT_CONFIRMED")
        desired.add(created)
        return {"status": "CREATED", "name": name, "uuid": created,
                "owned_tag_uuids": sorted(desired),
                "ownership_persistence_required": True,
                "delete_authorized": False}

    # Reordering is deliberately ignored: visual Kodi order is alphabetical.
    candidates = proposal["delete_owned_empty_candidates"]
    if not candidates or not allow_delete:
        return {"status": "DRY_RUN" if candidates else "UNCHANGED",
                "delete_candidates": candidates,
                "preserved": proposal["preserved_unowned_or_internal_empty"],
                "owned_tag_uuids": sorted(desired),
                "delete_authorized": False}
    target = candidates[0]
    # A second independent plan immediately before write, with a UUID
    # registry that must still match. No channel may reference the tag.
    recheck = plan(playlist, new_tags, new_channels, desired)
    if target not in recheck["delete_owned_empty_candidates"]:
        raise ReconcileBlocked("DELETE_RECHECK_BLOCKED")
    result = post("idnode/delete", {"uuid": target})
    if result is False:
        raise ReconcileBlocked("DELETE_FAILED")
    final_tags, final_channels = _snapshot(read_snapshot)
    final_plan = plan(playlist, final_tags, final_channels, desired - {target})
    _assert_identity(tags, final_tags, set(), {target})
    if target in {t["uuid"] for t in final_tags["entries"]}:
        raise ReconcileBlocked("DELETE_NOT_CONFIRMED")
    desired.remove(target)
    return {"status": "DELETED", "uuid": target,
            "owned_tag_uuids": sorted(desired),
            "ownership_persistence_required": True,
            "delete_authorized": True}
