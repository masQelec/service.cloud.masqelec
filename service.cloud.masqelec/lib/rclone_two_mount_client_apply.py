# -*- coding: utf-8 -*-
"""Opt-in CLIENT v2 recovery composition. Disabled and unconnected to Kodi.

This module joins the durable file adapter with the exact-account systemd
adapter. It never fetches OAuth or decides that an AUTH error occurred.
The already-verified candidate must be supplied by an explicitly authorized
caller. Production activation additionally requires a separate release gate.
"""
import os

from lib import constants
from lib import rclone_two_mount_client_file_ops as files
from lib import rclone_two_mount_client_systemd as systemd
from lib import rclone_two_mount_client_transaction as transaction
from lib import rclone_two_mount_client_runtime as runtime
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_boot_guard as guard
from lib import rclone_two_mount_kodi_idle as kodi_idle


def _is_root():
    """Isolated privilege gate; does not alter filesystem ownership checks."""
    return os.geteuid() == 0


def apply_verified(prepared, *, authorized=False, verified_probe=False,
                   rpc_call=None, media_check=None, adapter_factory=None,
                   account_path=None, journal_dir=None):
    """Apply one verified CLIENT candidate while holding its durable lock.

    Default: BLOCKED_NOT_AUTHORIZED, zero filesystem/network/systemd IO.
    Only intended as a controlled integration entrypoint, not a periodic
    service worker. Kodi playback is checked again before STOP.
    """
    if authorized is not True or verified_probe is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if (getattr(constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED", False)
            is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True or
            rollout.mode(True) != "active"):
        return "BLOCKED_RELEASE_GATES"
    if not _is_root():
        return "BLOCKED_NOT_ROOT"
    if not isinstance(prepared, dict):
        return "BLOCKED_CANDIDATE"
    index = prepared.get("account_index")
    if type(index) is not int or index not in (0, 1):
        return "BLOCKED_CANDIDATE"
    if not callable(media_check) or not kodi_idle.is_playback_idle(rpc_call):
        return "BLOCKED_PLAYBACK_OR_MEDIA"
    if guard.client_recovery_pending():
        return "BLOCKED_UNFINISHED_RECOVERY"
    location = (account_path if account_path is not None
                else plan.ACCOUNT_CONFS[index])
    folder = (journal_dir if journal_dir is not None
              else os.path.join(guard.CLIENT_TXN_PARENT,
                                "account{}".format(index + 1)))
    try:
        if journal_dir is None:
            files.provision_private_journal(folder)
        constructor = adapter_factory or systemd.AccountSystemd
        machine = constructor(index, enabled=True, media_check=media_check)
        operations = files.AccountFileOps(
            index, account_path=location, journal_dir=folder,
            stop=machine.stop, quiescent=machine.quiescent,
            start=machine.start, healthy=machine.healthy,
            enabled=True)
        # Secure parent/journal directories are *not* created automatically.
        # A separate authorized installer must provision them at 0700.
        with files.locked(folder):
            if not kodi_idle.is_playback_idle(rpc_call):
                return "BLOCKED_PLAYBACK_OR_MEDIA"
            return transaction.execute(
                prepared, authorized=True, verified_probe=True,
                playback_idle=True, operations=operations)
    except (OSError, ValueError, TypeError, RuntimeError,
            PermissionError, BlockingIOError):
        return "MANUAL_RECOVERY_REQUIRED"


def _get_role():
    from lib import device_utils
    return device_utils.get_device_role()


def recover_one(*, account_index, auth_status, read_sources, head, get,
                probe, key, rpc_call, media_check, authorized=False,
                adapter_factory=None, account_path=None, journal_dir=None):
    """Verify GitHub MQC2 and commit one account, only behind release flags.

    This is not a Kodi worker. Caller must independently attest AUTH and
    provide authenticated GET/HEAD, temporary-copy probe and media-check.
    Returned text is a closed status, NEVER candidate OAuth bytes.
    """
    if authorized is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if (getattr(constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED", False)
            is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True):
        return "BLOCKED_RELEASE_GATES"
    if _get_role() != "CLIENT":
        return "BLOCKED_NOT_CLIENT"
    if rollout.mode(True) != "active":
        return "BLOCKED_NOT_ACTIVE"
    if not callable(media_check) or not kodi_idle.is_playback_idle(rpc_call):
        return "BLOCKED_PLAYBACK_OR_MEDIA"
    if guard.client_recovery_pending():
        return "BLOCKED_UNFINISHED_RECOVERY"
    result = runtime.verify_once(
        account_index=account_index, auth_status=auth_status,
        read_sources=read_sources, head=head, get=get, probe=probe,
        key=key, release_authorized=True, return_candidate=True)
    if not isinstance(result, dict):
        return result
    if result.get("status") != "candidate_probe_verified":
        return "BLOCKED_CANDIDATE"
    return apply_verified(
        result["prepared"], authorized=True, verified_probe=True,
        rpc_call=rpc_call, media_check=media_check,
        adapter_factory=adapter_factory,
        account_path=account_path, journal_dir=journal_dir)
