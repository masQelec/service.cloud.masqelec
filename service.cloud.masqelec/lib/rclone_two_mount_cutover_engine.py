# -*- coding: utf-8 -*-
"""Motor de transición 4 FUSE -> 2 FUSE/4 bind, SIN adaptador operativo.

El motor no invoca systemctl, no lee OAuth ni escribe rutas Kodi.
Solo coordina operaciones de un adaptador explícito, que deberá incluir
journal persistente, bloqueo exclusivo, snapshots privados, validación
de reproducción inactiva y recuperación tras reinicio. En esta fase no
existe adaptador live y no hay integración en el arranque.
"""

class CutoverAbort(Exception):
    """Error esperado sin mensajes de sistema ni secretos."""


def _safe(fn):
    try:
        return fn() is True
    except Exception:
        return False


def _attempt(fn):
    try:
        fn()
        return True
    except Exception:
        return False


def run(adapter, *, release_authorized=False,
        playback_idle=False, rollback_ready=False):
    """Coordina o revierte con adaptador inyectado.

    Ningún adaptador de producción está conectado en esta fase.
    El éxito de este motor con mocks no certifica cutover real.
    """
    if any(type(v) is not bool for v in (
            release_authorized, playback_idle, rollback_ready)):
        return "BLOCKED_INVALID_GATES"
    if not release_authorized:
        return "BLOCKED_NOT_AUTHORIZED"
    if not playback_idle:
        return "BLOCKED_PLAYBACK_NOT_VERIFIED"
    if not rollback_ready:
        return "BLOCKED_ROLLBACK_NOT_READY"

    # Validar antes de cualquier operación mutable; las fuentes serán
    # verificadas de nuevo por el adaptador con bloqueo exclusivo real.
    if not _safe(adapter.legacy_preflight):
        return "BLOCKED_LEGACY_PREFLIGHT"
    if not _safe(adapter.playback_still_idle):
        return "BLOCKED_PLAYBACK_CHANGED"
    if not _safe(adapter.prepare_durable_rollback):
        return "BLOCKED_ROLLBACK_PREPARATION"

    try:
        # Journal persistente ANTES de parar legacy, si se implementa I/O.
        adapter.mark_cutover_started()
        adapter.stop_legacy()
        if not _safe(adapter.legacy_fully_unmounted):
            raise CutoverAbort("legacy still mounted")
        adapter.install_current_v2()
        adapter.start_fuse()
        if not _safe(adapter.fuse_ready):
            raise CutoverAbort("fuse not ready")
        adapter.start_binds()
        if not _safe(adapter.complete_health):
            raise CutoverAbort("2fuse/4bind failed")
        if not _safe(adapter.playback_still_idle):
            raise CutoverAbort("playback race")
        # El marcador ACTIVE es último; antes no se puede aceptar v2.
        adapter.mark_active()
        return "ACTIVE"
    except Exception:
        # Si se interrumpe el proceso por SIGKILL/reinicio, la fase durable
        # debe forzar modo unsafe + recuperación explícita al arrancar.
        # No ejecutar operaciones destructivas de rollback si falla umount.
        if not _attempt(adapter.stop_binds):
            return "MANUAL_RECOVERY_REQUIRED"
        if not _attempt(adapter.stop_fuse):
            return "MANUAL_RECOVERY_REQUIRED"
        if not _safe(adapter.new_fully_unmounted):
            return "MANUAL_RECOVERY_REQUIRED"
        # La conciliación debe leer account*.conf tras parar rclone,
        # y preservar Google Drive y crypt del canónico existente.
        if not _attempt(adapter.reconcile_and_restore_legacy):
            return "MANUAL_RECOVERY_REQUIRED"
        if not _attempt(adapter.start_legacy):
            return "MANUAL_RECOVERY_REQUIRED"
        if not _safe(adapter.legacy_healthy):
            return "MANUAL_RECOVERY_REQUIRED"
        if not _attempt(adapter.mark_legacy_restored):
            return "MANUAL_RECOVERY_REQUIRED"
        return "ROLLED_BACK"
