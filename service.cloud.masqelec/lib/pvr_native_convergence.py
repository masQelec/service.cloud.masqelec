"""G3-X: fail-closed, read-only descriptive Kodi/TVH convergence audit.

This is NOT a CUID-to-TVH/Kodi identity mapping. Name equality can never
authorize channel deletion, Kodi SQLite changes or skipping a legacy reset.
No IO or mutations: callers provide complete API snapshots.
"""
from collections import Counter

MAX_CHANNELS = 20000


def _inventory(rows, name_field, id_field):
    if not isinstance(rows, list) or not 0 < len(rows) <= MAX_CHANNELS:
        raise ValueError("INCOMPLETE_INVENTORY")
    names = Counter()
    identities = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("INVALID_CHANNEL_ROW")
        name = row.get(name_field)
        ident = row.get(id_field)
        if not isinstance(name, str) or not name.strip():
            raise ValueError("MISSING_NAME")
        if type(ident) not in (str, int) or not str(ident).strip():
            raise ValueError("MISSING_ID")
        # Kodi channelid may be integer; TVH uuid is a string.
        if type(ident) is int and ident < 0:
            raise ValueError("INVALID_ID")
        if ident in identities:
            raise ValueError("DUPLICATE_ID")
        identities.add(ident)
        names[name.strip()] += 1
    return names


def classify(tvh_rows, kodi_rows, *, tvh_total=None, kodi_total=None):
    """Report descriptive convergence, never authorize any mutation.

    A total is mandatory for each API to reject truncated/paginated data.
    Fail closed on duplicate names: descriptive comparisons cannot establish
    channel identity and could mask an orphan swapped for another channel.
    """
    result = {
        "status": "BLOCKED",
        "reason": "UNVERIFIED_INPUT",
        "tvh_channels": 0,
        "kodi_channels": 0,
        "ambiguous_names": 0,
        "native_orphan_removal_proven": False,
        "cuid_mapping_proven": False,
        "delete_authorized": False,
        "cutover_authorized": False,
    }
    if (type(tvh_total) is not int or type(kodi_total) is not int
            or not isinstance(tvh_rows, list) or not isinstance(kodi_rows, list)
            or tvh_total != len(tvh_rows) or kodi_total != len(kodi_rows)):
        result["reason"] = "INCOMPLETE_API_SNAPSHOT"
        return result
    try:
        tvh = _inventory(tvh_rows, "name", "uuid")
        kodi = _inventory(kodi_rows, "label", "channelid")
    except ValueError as exc:
        result["reason"] = str(exc)
        return result

    result["tvh_channels"] = len(tvh_rows)
    result["kodi_channels"] = len(kodi_rows)
    result["ambiguous_names"] = sum(n for n in tvh.values() if n > 1) + sum(
        n for n in kodi.values() if n > 1)
    if tvh != kodi:
        result["status"] = "DESCRIPTIVE_MISMATCH"
        result["reason"] = "NAMES_OR_MULTIPLICITIES_DIFFER"
    elif result["ambiguous_names"]:
        result["status"] = "DESCRIPTIVE_AMBIGUOUS"
        result["reason"] = "DUPLICATE_NAMES_IDENTITY_UNPROVEN"
    else:
        result["status"] = "DESCRIPTIVE_MATCH"
        result["reason"] = "SINGLE_SNAPSHOT_NOT_IDENTITY_PROOF"
    return result
