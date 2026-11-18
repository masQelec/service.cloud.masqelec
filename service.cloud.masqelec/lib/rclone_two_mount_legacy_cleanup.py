# -*- coding: utf-8 -*-
"""Retirada idempotente de 4 unit files legacy TRAS ACTIVE verificado.

No borra una configuración OAuth, .strm ni ningún montaje. Los respaldos
privados del journal se conservan para una restauración futura. La función
no es llamada desde Kodi hasta habilitar la release y sus gates.
"""
import os
import stat

from lib import rclone_two_mount_atomic_install as atomic
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_startup_stage as stage

DONE_NAME = "legacy-unit-cleanup.done"
DONE_BYTES = b"complete\n"


def _saved_unit(folder, name):
    raw, _ = stage._read_file(os.path.join(folder, name), confidential=True)
    if b"[Service]" not in raw or b"ExecStart=" not in raw:
        raise ValueError("Invalid legacy backup")
    return raw


def _verified_unit(path, expected):
    """No seguir symlinks; comprobar propietario, permisos y contenido."""
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.geteuid()
            or stat.S_IMODE(info.st_mode) not in (0o600, 0o644)):
        raise ValueError("Legacy unit changed or unsafe")
    actual, _ = stage._read_file(path)
    if actual != expected:
        raise ValueError("Legacy unit differs from durable backup")


def retire_after_active(adapter, *, authorized=False):
    """Completar la limpieza, incluso si un reboot la dejó a medias.

    No se desmonta ni para NINGÚN servicio. Se exige ACTIVE y salud de
    seis servicios cuando queden archivos que retirar. Las unidades
    antiguas deben estar inactivas y deshabilitadas. Se revalida TODO el
    inventario antes de borrar el primero; un fallo parcial se reintenta
    idempotentemente después. No reintroduce legacy automáticamente.
    """
    if (authorized is not True or
            getattr(adapter, "enabled", False) is not True):
        return "BLOCKED_NOT_AUTHORIZED"
    if rollout.mode(True, state_path=adapter.state_path) != "active":
        return "BLOCKED_NOT_ACTIVE"
    try:
        with journal.locked(adapter.txn_parent):
            target = os.path.join(adapter.txn_parent, rollout.CANDIDATE_ID)
            if journal.phase(target) != "active":
                return "BLOCKED_JOURNAL_NOT_ACTIVE"
            backup = {unit: _saved_unit(target, unit)
                      for unit in rollout.LEGACY_SERVICES}
            atomic._trusted_folder(adapter.unit_dir)
            done = os.path.join(target, DONE_NAME)
            if os.path.lexists(done):
                if any(os.path.lexists(os.path.join(adapter.unit_dir, unit))
                       for unit in rollout.LEGACY_SERVICES):
                    return "BLOCKED_DONE_MARKER_CONFLICT"
                if stage._read_file(done, confidential=True)[0] != DONE_BYTES:
                    return "BLOCKED_DONE_MARKER_CONFLICT"
                return "ALREADY_CLEAN"

            # Jamás retirar si hay drop-ins de operador o seguridad.
            if any(os.path.lexists(os.path.join(
                    adapter.unit_dir, unit + ".d"))
                    for unit in rollout.LEGACY_SERVICES):
                return "BLOCKED_LEGACY_DROPINS"

            present = []
            for unit in rollout.LEGACY_SERVICES:
                path = os.path.join(adapter.unit_dir, unit)
                if not os.path.lexists(path):
                    continue  # Crash tras retirar parcialmente: reanudable.
                _verified_unit(path, backup[unit])
                present.append((path, backup[unit]))

            # Incluso cuando un crash dejó ya los cuatro archivos ausentes,
            # NO confirmar la retirada sin seis montajes sanos y ninguna
            # unidad legacy activa/enabled. Evita finalizar sobre v2 roto.
            if not adapter.complete_health():
                return "BLOCKED_V2_UNHEALTHY"
            for unit in rollout.LEGACY_SERVICES:
                if adapter._active(unit):
                    return "BLOCKED_LEGACY_RUNNING"
                # 'is-enabled --quiet' no diferencia disabled de fallo
                # de systemd. Solo estados explícitos y conocidos.
                state = adapter.legacy_unit_file_state(unit)
                allowed = ("disabled",) if os.path.lexists(
                    os.path.join(adapter.unit_dir, unit)) else (
                        "disabled", "not-found")
                if state not in allowed:
                    return "BLOCKED_LEGACY_ENABLED_OR_UNKNOWN"
            for path, original in present:
                atomic.remove_if_identical(path, original)
            adapter._systemctl("daemon-reload")
            journal._write_new(done, DONE_BYTES)
            journal._sync(target)
            return "CLEANED"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError,
            BlockingIOError):
        return "BLOCKED_CLEANUP_INCOMPLETE"
