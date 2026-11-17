# -*- coding: utf-8 -*-
"""P0-D: verificación de readback CAS autenticado, PURA y sin transporte.

No realiza GET/PUT, no interpreta un PUT 200 como autorización, no guarda
credenciales y no está conectada al addon. No imprimir datos ni huellas.
"""
import hmac
import re

from lib import rclone_two_mount_publish_guard as publisher
from lib import rclone_token_policy as policy

_SHA = re.compile(r"[0-9a-f]{40}\Z")


def confirm_readback(expected_canonical, expected_encrypted, readback_body, key,
                     expected_put_commit, branch_head_before,
                     branch_head_after, *, put_accepted=False):
    """Verifica una supuesta publicación completada, para LAB sintético.

    El llamador debe haber recuperado el contents GET desde el HEAD actual
    y reconsultado HEAD después; aquí no se establece que sea un GET fresco.
    Un resultado 'verified_lab_only' JAMÁS permite release.
    """
    if put_accepted is not True:
        return "blocked_no_accepted_put"
    if not all(isinstance(x, str) and _SHA.fullmatch(x) for x in (
            expected_put_commit, branch_head_before, branch_head_after)):
        return "blocked_invalid_revision"
    if (branch_head_before != expected_put_commit or
            branch_head_after != branch_head_before):
        return "blocked_remote_revision_drift"
    if (type(expected_canonical) is not bytes or
            type(expected_encrypted) is not bytes or
            not expected_canonical or not expected_encrypted):
        return "blocked_invalid_candidate"
    try:
        policy.validate_master_layout(expected_canonical)
        expected_blob_sha = publisher.git_blob_sha(expected_encrypted)
        readback = publisher.decode_remote_contents(readback_body, key)
    except (ValueError, TypeError, UnicodeError):
        return "blocked_readback_auth_or_layout"
    if not hmac.compare_digest(readback["sha"], expected_blob_sha):
        return "blocked_remote_blob_mismatch"
    if not hmac.compare_digest(readback["canonical"], expected_canonical):
        return "blocked_remote_content_mismatch"
    return "verified_lab_only"
