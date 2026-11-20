# -*- coding: utf-8 -*-
"""Freno de arranque ante transición FUSE interrumpida.

Solo lee la existencia/estado del journal privado y el marcador local.
No inicia, desmonta ni reinstala servicios. No es un recuperador operativo.
En ausencia de una transacción, no cambia el comportamiento legacy.
"""
import os
import stat

from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_client_file_ops as client_files
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_recovery_units as recovery_units

TXN_PARENT = "/storage/.config/masqelec/rclone-v2-transaction"
CLIENT_TXN_PARENT = "/storage/.config/masqelec/rclone-v2-client-recovery"


def client_recovery_pending(parent=None):
    """A v2 CLIENT with a partial recovery must not resume normal tasks."""
    parent = CLIENT_TXN_PARENT if parent is None else parent
    try:
        if not os.path.lexists(parent):
            return False
        meta = os.lstat(parent)
        if (not stat.S_ISDIR(meta.st_mode) or
                stat.S_IMODE(meta.st_mode) != 0o700 or
                meta.st_uid != os.geteuid()):
            return True
        return any(client_files.recovery_pending(
            os.path.join(parent, "account{}".format(i)),
            account_index=i-1) for i in (1, 2))
    except (OSError, ValueError, TypeError, UnicodeError):
        return True



def _safe_file(path, mode, *, max_size=1024 * 1024):
    try:
        info = os.lstat(path)
        return (stat.S_ISREG(info.st_mode)
                and stat.S_IMODE(info.st_mode) == mode
                and info.st_uid == os.geteuid()
                and 0 < info.st_size <= max_size)
    except OSError:
        return False


def _legacy_recovery_complete(target, unit_dir):
    """Inspecciona 4 drop-ins sin revelar ni tocar credenciales secretas."""
    recovery = os.path.join(
        target, "canonical-recovery-candidate.conf")
    names = rollout.LEGACY_SERVICES
    dirs = [os.path.join(unit_dir, unit + ".d") for unit in names]
    if not os.path.lexists(recovery):
        # Rollback sin rotación: no debe haber overrides parciales.
        return not any(os.path.lexists(d) for d in dirs)
    if not _safe_file(recovery, 0o600):
        return False
    try:
        legacy_units = {}
        for name in names:
            unit_file = os.path.join(target, name)
            if not _safe_file(unit_file, 0o600):
                return False
            with open(unit_file, "rb") as f:
                legacy_units[name] = f.read(1024 * 1024 + 1)
        expected = recovery_units.overrides(legacy_units, recovery)
        for name, folder in zip(names, dirs):
            journal._private_dir(folder)
            dropin = os.path.join(folder, recovery_units.DROPIN)
            content = expected[name]
            if not _safe_file(dropin, 0o644, max_size=65536):
                return False
            with open(dropin, "rb") as f:
                if f.read(65537) != content:
                    return False
        return True
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


def recovery_required(*, parent=TXN_PARENT, state_path=rollout.STATE_PATH,
                      feature_allowed=False,
                      unit_dir="/storage/.config/system.d"):
    """True bloquea arranque cloud/escaneo, incluso si estado es ilegible.

    El estado active solo es aceptable con feature_allowed=True y journal
    active. Su salud real se comprueba después mediante mountinfo.
    """
    if client_recovery_pending():
        return True
    target = os.path.join(parent, rollout.CANDIDATE_ID)
    try:
        present = os.path.lexists(target)
        marker = os.path.lexists(state_path)
        if not present:
            return marker
        phase = journal.phase(target)
        if phase == "prepared":
            return marker
        if phase == "legacy_restored":
            return marker or not _legacy_recovery_complete(target, unit_dir)
        if phase == "active":
            return not (feature_allowed is True and marker and
                        rollout.mode(True, state_path=state_path) == "active")
        return True
    except (OSError, ValueError, TypeError, UnicodeError):
        return True
