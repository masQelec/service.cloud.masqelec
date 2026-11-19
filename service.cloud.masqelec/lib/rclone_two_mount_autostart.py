# -*- coding: utf-8 -*-
"""Arranque/reintento local automático de 4 FUSE -> 2 FUSE + 4 bind.

NO opera por defecto. Solo el addon de una release aprobada activará los
flags independientes. No publica credenciales ni modifica archivos STRM.
"""
import os

from lib import constants
from lib import rclone_two_mount_kodi_idle as kodi_idle
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_legacy_cleanup as cleanup
from lib import rclone_two_mount_media_samples as media_samples
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_active_maintenance as maintenance
from lib import rclone_two_mount_boot_install as boot_install

_STATUSES = frozenset({
    "DISABLED", "BLOCKED_RELEASE_GATES", "BLOCKED_NOT_ROOT",
    "BLOCKED_KODI_RPC", "BLOCKED_MEDIA_FIXTURES",
    "BLOCKED_UNSAFE_STATE", "BLOCKED_PREPARED_STATE",
    "DEFERRED_PLAYBACK_ACTIVE", "BLOCKED_UNEXPECTED_MODE",
    "BLOCKED_LOCAL_ERROR", "ACTIVE_PENDING_CLEANUP",
    "ACTIVE_VERIFIED_LEGACY_RETIRED", "ACTIVE_CLEAN_ALREADY",
    "ROLLED_BACK", "BLOCKED_MANUAL_RECOVERY_REQUIRED",
    "BLOCKED_RECOVERY_NOT_ENABLED",
    "BLOCKED_LEGACY_PREFLIGHT", "BLOCKED_ROLLBACK_PREPARATION",
    "BLOCKED_PLAYBACK_CHANGED", "BLOCKED_PLAYBACK_NOT_VERIFIED",
    "BLOCKED_FEATURE_DISABLED", "MANUAL_RECOVERY_REQUIRED",
    "CLEANED", "ALREADY_CLEAN", "BLOCKED_NOT_AUTHORIZED",
    "BLOCKED_NOT_ACTIVE", "BLOCKED_JOURNAL_NOT_ACTIVE",
    "BLOCKED_DONE_MARKER_CONFLICT", "BLOCKED_LEGACY_DROPINS",
    "BLOCKED_V2_UNHEALTHY", "BLOCKED_LEGACY_RUNNING",
    "BLOCKED_LEGACY_ENABLED_OR_UNKNOWN",
    "BLOCKED_CLEANUP_INCOMPLETE", "BLOCKED_NOT_INTERRUPTED",
    "BLOCKED_ROLLBACK_NOT_READY", "BLOCKED_NOT_AUTHORIZED",
    "ACTIVE_HEALTHY", "ACTIVE_REPAIRED", "BLOCKED_ACTIVE_MAINTENANCE",
    "BLOCKED_LEGACY_MOUNT", "BLOCKED_ROOT_ACTIVE_UNMOUNTED",
    "BLOCKED_ROOT_OCCUPIED", "BLOCKED_ROOT_NOT_READY",
    "BLOCKED_ORPHAN_BIND",
    "BLOCKED_BIND_ACTIVE_UNMOUNTED", "BLOCKED_BIND_OCCUPIED",
    "BLOCKED_BOOT_INSTALL_NOT_AUTHORIZED",
    "BLOCKED_BOOT_INSTALL_UNVERIFIED",
    "BLOCKED_BOOT_INSTALL_CONFLICT",
    "BLOCKED_BOOT_SCRIPT_MISSING", "BLOCKED_BOOT_INSTALL_FAILED",
    "BLOCKED_BOOT_RECOVERY_NOT_ARMED",
    "BLOCKED_V2_CONFIG_NOT_PUBLISHED",
})


def _valid_media_paths(paths):
    if not isinstance(paths, (tuple, list)) or len(paths) != 2:
        return False
    for number, path in enumerate(paths, 1):
        if (not isinstance(path, str) or
                not os.path.isabs(path) or os.path.normpath(path) != path):
            return False
        allowed = (
            "/storage/.mnt/videos/{}/".format(number),
            "/storage/.mnt/tvshows/{}/".format(number),
        )
        if not path.startswith(allowed) or path.endswith("/"):
            return False
    return True


def tick(rpc_call, *, adapter_factory=None):
    """Una evaluación del primer arranque o de una migración diferida.

    La migración del mismo equipo es transaccional; otras instalaciones
    pueden actualizarse en otro momento sin ninguna acción sobre ellas.
    No se crean archivos ni locks si los flags están desactivados.
    """
    if getattr(constants, "RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED", False) is not True:
        return "DISABLED"
    if (getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED", False)
            is not True):
        return "BLOCKED_RELEASE_GATES"
    if os.geteuid() != 0:
        return "BLOCKED_NOT_ROOT"
    if not callable(rpc_call):
        return "BLOCKED_KODI_RPC"
    try:
        mode = rollout.mode(True)
        maker = (adapter_factory if adapter_factory is not None
                 else live.LocalAdapter)
        if mode not in ("legacy", "prepared", "active", "unsafe"):
            return "BLOCKED_UNEXPECTED_MODE"
        if mode == "prepared":
            # Un journal prepared anterior no debe eliminarse ciegamente.
            return "BLOCKED_PREPARED_STATE"
        # La recuperación de un corte unsafe NO depende de que el catálogo
        # local aún contenga dos vídeos válidos: restaurar los cuatro FUSE
        # sigue siendo prioritario.
        if mode in ("legacy", "unsafe") and not kodi_idle.is_playback_idle(
                rpc_call):
            return "DEFERRED_PLAYBACK_ACTIVE"
        if mode == "unsafe":
            if (getattr(constants, "RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED",
                        False) is not True):
                return "BLOCKED_RECOVERY_NOT_ENABLED"
            adapter = maker(rpc_call=rpc_call, live_enabled=True,
                            known_media_files=())
            recovered = live.recover_with_local_lock(
                adapter, authorized=True, verified_rollback=True)
            return recovered if recovered in _STATUSES else (
                "BLOCKED_MANUAL_RECOVERY_REQUIRED")
        if mode == "active":
            # Existing v2 is self-managed even if the local .strm catalog
            # currently has no two known samples. Only first cutover and
            # irreversible legacy retirement require media sample reads.
            adapter = maker(rpc_call=rpc_call, live_enabled=True,
                            known_media_files=())
            maintained = maintenance.ensure_active(adapter, authorized=True)
            if maintained not in ("ACTIVE_HEALTHY", "ACTIVE_REPAIRED"):
                return maintained if maintained in _STATUSES else (
                    "BLOCKED_ACTIVE_MAINTENANCE")
            if (getattr(constants, "RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED",
                        False) is not True):
                return "ACTIVE_PENDING_CLEANUP"
            known = getattr(constants, "RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES", ())
            if known == ():
                known = media_samples.discover()
            if not _valid_media_paths(known):
                return "ACTIVE_PENDING_CLEANUP"
            adapter.known_media_files = tuple(known)
            result = cleanup.retire_after_active(
                adapter, authorized=True)
            return {
                "CLEANED": "ACTIVE_VERIFIED_LEGACY_RETIRED",
                "ALREADY_CLEAN": "ACTIVE_CLEAN_ALREADY",
            }.get(result, result if result in _STATUSES
                  else "BLOCKED_LOCAL_ERROR")
        # Starting the cutover without crash/reboot recovery enabled could
        # leave all four legacy FUSE disabled after power loss. Fail before
        # media discovery, journal, systemd changes, or mount operations.
        if (getattr(constants, "RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED",
                    False) is not True):
            return "BLOCKED_BOOT_RECOVERY_NOT_ARMED"
        # The v2 MQC2 endpoint must exist BEFORE legacy units are stopped.
        # Once marked active, CLIENT never falls back to legacy MQC2.
        from lib import rclone_two_mount_v2_publication as publication
        if not publication.available():
            # Only MASTER may create v2 MQC2. If CLIENT updates before
            # MASTER, leave its four FUSE and retry later on the same
            # addon version: no partial per-device migration.
            from lib import rclone_two_mount_master_runtime as master_runtime
            if (master_runtime._get_role() == "MASTER"
                    and getattr(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
                                False) is True):
                publish = master_runtime.publish_from_legacy_before_cutover(
                    authorized=True)
                if publish not in ("created_verified", "unchanged",
                                   "updated_verified"):
                    return "BLOCKED_V2_CONFIG_NOT_PUBLISHED"
            if not publication.available():
                return "BLOCKED_V2_CONFIG_NOT_PUBLISHED"
        # First migration demands two independent, locally discoverable
        # media fixtures before disabling a single legacy FUSE.
        known = getattr(constants, "RCLONE_TWO_MOUNT_KNOWN_MEDIA_FILES", ())
        if known == ():
            known = media_samples.discover()
        if not _valid_media_paths(known):
            return "BLOCKED_MEDIA_FIXTURES"
        adapter = maker(rpc_call=rpc_call, live_enabled=True,
                        known_media_files=known)
        boot_ready = boot_install.ensure_installed(adapter, authorized=True)
        if boot_ready != "READY":
            return boot_ready if boot_ready in _STATUSES else (
                "BLOCKED_BOOT_INSTALL_UNVERIFIED")
        outcome = live.execute_with_local_lock(
            adapter, authorized=True, verified_rollback=True)
        if outcome == "ACTIVE":
            if (getattr(constants, "RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED",
                        False) is not True):
                return "ACTIVE_PENDING_CLEANUP"
            cleaned = cleanup.retire_after_active(adapter, authorized=True)
            return {
                "CLEANED": "ACTIVE_VERIFIED_LEGACY_RETIRED",
                "ALREADY_CLEAN": "ACTIVE_CLEAN_ALREADY",
            }.get(cleaned, cleaned if cleaned in _STATUSES
                  else "BLOCKED_LOCAL_ERROR")
        return outcome if outcome in _STATUSES else (
            "BLOCKED_MANUAL_RECOVERY_REQUIRED")
    except (OSError, ValueError, RuntimeError, TypeError,
            BlockingIOError):
        return "BLOCKED_LOCAL_ERROR"
