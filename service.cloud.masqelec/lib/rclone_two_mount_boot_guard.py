# -*- coding: utf-8 -*-
"""Freno de arranque ante transición FUSE interrumpida.

Solo lee la existencia/estado del journal privado y el marcador local.
No inicia, desmonta ni reinstala servicios. No es un recuperador operativo.
En ausencia de una transacción, no cambia el comportamiento legacy.
"""
import os

from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_rollout as rollout

TXN_PARENT = "/storage/.config/masqelec/rclone-v2-transaction"


def recovery_required(*, parent=TXN_PARENT, state_path=rollout.STATE_PATH,
                      feature_allowed=False):
    """True bloquea arranque cloud/escaneo, incluso si estado es ilegible.

    El estado active solo es aceptable con feature_allowed=True y journal
    active. Su salud real se comprueba después mediante mountinfo.
    """
    target = os.path.join(parent, rollout.CANDIDATE_ID)
    try:
        present = os.path.lexists(target)
        marker = os.path.lexists(state_path)
        if not present:
            return marker
        phase = journal.phase(target)
        if phase in ("prepared", "legacy_restored"):
            return marker
        if phase == "active":
            return not (feature_allowed is True and marker and
                        rollout.mode(True, state_path=state_path) == "active")
        return True
    except (OSError, ValueError, TypeError, UnicodeError):
        return True
