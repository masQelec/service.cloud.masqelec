# -*- coding: utf-8 -*-
"""Recover an interrupted CLIENT OAuth transaction after restart.

No implicit execution at import. The caller MUST supply a trusted per-account
service adapter, authorize a reboot recovery, and arrange early boot ordering
BEFORE Kodi/automatic rclone units. A 'rolled_back' state is written only
after original bytes AND actual media health have been independently verified.
"""
import json
import os

from lib import rclone_two_mount_client_file_ops as files


def restore_interrupted(index, *, account_path, journal_dir, services,
                        authorized=False):
    """Rollback a durable interrupted transaction under exclusive file lock.

    Returns status strings only. If unsafe, leaves journal pending and never
    claims recovery; does not clear backups or manage the other account.
    """
    if authorized is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if type(index) is not int or index not in (0, 1):
        return "BLOCKED_ACCOUNT"
    if os.path.basename(account_path) != "account{}.conf".format(index + 1):
        return "BLOCKED_ACCOUNT"
    if not all(callable(getattr(services, name, None))
               for name in ("stop", "quiescent", "start", "healthy")):
        return "BLOCKED_OPERATIONS"
    try:
        with files.locked(journal_dir):
            state_path = os.path.join(journal_dir, "state.json")
            if not os.path.lexists(state_path):
                return ("MANUAL_RECOVERY_REQUIRED" if
                        files.recovery_pending(journal_dir)
                        else "BLOCKED_NO_TRANSACTION")
            raw, _ = files._read(state_path)
            obj = json.loads(raw)
            if (type(obj) is not dict or
                    set(obj) != {"version", "account", "phase"} or
                    obj["version"] != 1 or
                    type(obj["account"]) is not int or
                    obj["account"] != index or
                    not isinstance(obj["phase"], str)):
                return "MANUAL_RECOVERY_REQUIRED"
            if obj["phase"] in ("committed", "rolled_back"):
                return "ALREADY_FINALIZED"
            allowed = ("prepared", "stop_requested", "install_requested",
                       "start_requested", "rollback_requested")
            if obj["phase"] not in allowed:
                return "MANUAL_RECOVERY_REQUIRED"
            backup = os.path.join(journal_dir,
                                  "account{}.bak".format(index + 1))
            original, _ = files._read(backup)
            # Stop target services before changing credentials: even after a
            # power failure systemd may have started the recovered writer.
            if services.stop(index) is not True:
                return "MANUAL_RECOVERY_REQUIRED"
            if services.quiescent(index) is not True:
                return "MANUAL_RECOVERY_REQUIRED"
            files._atomic(state_path, json.dumps({
                "version": 1, "account": index,
                "phase": "rollback_requested"
            }, sort_keys=True).encode("ascii"))
            files._atomic(account_path, original)
            if files._read(account_path)[0] != original:
                return "MANUAL_RECOVERY_REQUIRED"
            if services.start(index) is not True:
                return "MANUAL_RECOVERY_REQUIRED"
            if services.healthy(index) is not True:
                return "MANUAL_RECOVERY_REQUIRED"
            if files._read(account_path)[0] != original:
                return "MANUAL_RECOVERY_REQUIRED"
            files._atomic(state_path, json.dumps({
                "version": 1, "account": index, "phase": "rolled_back"
            }, sort_keys=True).encode("ascii"))
            return "ROLLED_BACK_VERIFIED"
    except (OSError, ValueError, KeyError, TypeError, RuntimeError,
            UnicodeError, BlockingIOError):
        return "MANUAL_RECOVERY_REQUIRED"
