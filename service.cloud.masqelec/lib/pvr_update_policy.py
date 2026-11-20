"""G3-Q: side-effect-free PVR update decision audit.

Classify a proposed legacy reset and its possible non-disruptive alternative.
A decision is diagnostic ONLY. Never use this module to authorize removal of
the legacy reset without a verified TVH refetch and Kodi PVR convergence gate.
"""


def classify(*, playlist_changed, db_mismatch, tvh_ready=None,
             refetch_confirmed=False, channel_identity_confirmed=False,
             group_links_confirmed=False, kodi_confirmed=False):
    inputs = (playlist_changed, db_mismatch, refetch_confirmed,
              channel_identity_confirmed, group_links_confirmed, kodi_confirmed)
    if any(type(item) is not bool for item in inputs):
        raise ValueError("INVALID_BOOLEAN_INPUT")
    if tvh_ready is not None and type(tvh_ready) is not bool:
        raise ValueError("INVALID_TVH_STATE")
    legacy_soft_reset = playlist_changed or db_mismatch
    if not legacy_soft_reset:
        return {
            "status": "NO_RESET_NEEDED",
            "legacy_soft_reset": False,
            "non_disruptive_cutover_authorized": False,
            "reason": "ALREADY_UNCHANGED",
        }
    if tvh_ready is not True:
        reason = "TVH_READY_NOT_PROVEN"
    elif not refetch_confirmed:
        reason = "M3U_REFETCH_NOT_PROVEN"
    elif not channel_identity_confirmed:
        reason = "CHANNEL_IDENTITY_NOT_PROVEN"
    elif not group_links_confirmed:
        reason = "CHANNEL_GROUP_LINKS_NOT_PROVEN"
    elif not kodi_confirmed:
        reason = "KODI_CONVERGENCE_NOT_PROVEN"
    else:
        # Evidence is only from caller; no automatic cutover is authorized.
        reason = "ALL_EVIDENCE_REQUIRES_MANUAL_CUTOVER_REVIEW"
    return {
        "status": "LEGACY_RESET_REQUIRED_UNTIL_VERIFIED",
        "legacy_soft_reset": True,
        "non_disruptive_cutover_authorized": False,
        "reason": reason,
    }
