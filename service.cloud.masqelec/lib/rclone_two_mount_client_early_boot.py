# -*- coding: utf-8 -*-
"""Recover unfinished CLIENT v2 account journals before Kodi starts.

Explicitly disabled by default. Uses the same optional early-boot unit as
legacy cutover recovery, but does not start/stop anything unless pending and
separately authorized. No OAuth, no GitHub, no Kodi RPC.
"""
import os

from lib import constants
from lib import rclone_two_mount_client_role as client_role
from lib import rclone_two_mount_boot_guard as guard
from lib import rclone_two_mount_client_file_ops as files
from lib import rclone_two_mount_client_crash_recovery as crash
from lib import rclone_two_mount_client_systemd as systemd
from lib import rclone_two_mount_early_boot_recovery as early
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_media_samples as samples
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout


def _is_root():
    return os.geteuid() == 0


def _get_role():
    """Standalone systemd Python cannot import Kodi's xbmcvfs."""
    from tools import rclone_two_mount_real_oauth_grouped_preflight as role_probe
    return role_probe._read_role_standalone()


def execute(*, authorized=False, proc_root="/proc", adapter_factory=None,
            media_paths=None, parent=None):
    """Restore pending CLIENT journals after root/Kodi/role/active checks.

    The live release must prove ordering BEFORE Kodi and reboots. The
    existing boot unit's 'Wants' prevents media faults blocking Kodi, but
    the mount guard blocks unsafe follow-up activity.
    """
    if authorized is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if (getattr(constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                False) is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                    False) is not True):
        return "BLOCKED_FEATURE_DISABLED"
    if not _is_root():
        return "BLOCKED_NOT_ROOT"
    if not client_role.allowed(_get_role()):
        return "BLOCKED_NOT_CLIENT"
    if rollout.mode(True) != "active":
        return "BLOCKED_NOT_ACTIVE"
    if not early.kodi_process_absent(proc_root):
        return "BLOCKED_KODI_RUNNING_OR_UNKNOWN"
    base = guard.CLIENT_TXN_PARENT if parent is None else parent
    try:
        if not guard.client_recovery_pending(base):
            return "NO_PENDING"
        known = media_paths if media_paths is not None else samples.discover()
        if (not isinstance(known, (tuple, list)) or len(known) != 2):
            return "BLOCKED_MEDIA"
        results = []
        for index in (0, 1):
            folder = os.path.join(base, "account{}".format(index + 1))
            if not files.recovery_pending(folder, index):
                continue
            if not early.kodi_process_absent(proc_root):
                return "BLOCKED_KODI_RUNNING_OR_UNKNOWN"
            maker = adapter_factory or systemd.AccountSystemd
            machine = maker(
                index, enabled=True,
                media_check=lambda i: live.LocalAdapter._probe_known_media(
                    known[i]) if i in (0, 1) else False)
            result = crash.restore_interrupted(
                index, account_path=plan.ACCOUNT_CONFS[index],
                journal_dir=folder, services=machine, authorized=True)
            if result not in ("ROLLED_BACK_VERIFIED", "ALREADY_FINALIZED"):
                return "MANUAL_RECOVERY_REQUIRED"
            results.append(result)
        if guard.client_recovery_pending(base):
            return "MANUAL_RECOVERY_REQUIRED"
        return "ROLLED_BACK_VERIFIED" if results else "NO_PENDING"
    except (OSError, ValueError, TypeError, KeyError, RuntimeError,
            UnicodeError, BlockingIOError):
        return "MANUAL_RECOVERY_REQUIRED"
