"""G3-P: isolated, read-only PVR tag shadow audit for update_pvr.

No writes, no registry creation, no imports from live tvheadend addon. A mismatch
returns a diagnostic code and does not alter the existing update sequence.
"""
from .pvr_tag_plan import plan, PlanBlocked
from .pvr_tag_tvh_adapter import make_snapshot_reader, TvheadendAPIBlocked


def audit(playlist_file, api_get_json, read_text):
    try:
        playlist = read_text(playlist_file)
        reader = make_snapshot_reader(api_get_json)
        tags, channels = reader()
        result = plan(playlist, tags, channels)
        # Detect changes between both reads.
        tags_again, channels_again = reader()
        if (tags, channels) != (tags_again, channels_again):
            raise PlanBlocked("SNAPSHOT_DRIFT")
        return {
            "status": "PASS",
            "m3u_channels": result["m3u_channels"],
            "tvh_channels": result["tvh_channels"],
            "create_count": len(result["create_names"]),
            "unowned_empty_count": len(result["preserved_unowned_or_internal_empty"]),
            "index_mismatch_diagnostic": len(result["reorder_candidates"]),
            "write_executed": False,
        }
    except (PlanBlocked, TvheadendAPIBlocked, OSError, ValueError,
            UnicodeError, TypeError, KeyError) as exc:
        return {"status": "BLOCKED", "reason": type(exc).__name__,
                "write_executed": False}
