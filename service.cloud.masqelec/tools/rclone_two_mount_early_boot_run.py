# -*- coding: utf-8 -*-
"""Systemd early-boot runner: recovery failure is nonfatal for KodiELEC.

Only an explicitly authorized release can mutate mounts. A nonzero Kodi
startup dependency is intentionally avoided: media is optional.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import constants
from lib import rclone_two_mount_client_role as client_role
from lib import rclone_two_mount_early_boot_recovery as early

_ALLOWED = frozenset({
    "NO_PENDING", "ACTIVE_NO_RECOVERY", "ROLLED_BACK",
    "BLOCKED_NOT_AUTHORIZED", "BLOCKED_FEATURE_DISABLED",
    "BLOCKED_NOT_ROOT", "BLOCKED_INCONSISTENT_STATE",
    "BLOCKED_KODI_RUNNING_OR_UNKNOWN", "BLOCKED_STATE_CHANGED",
    "MANUAL_RECOVERY_REQUIRED", "BLOCKED_NOT_CLIENT",
    "BLOCKED_NOT_ACTIVE", "BLOCKED_MEDIA",
})



def _dev_fake_boot_lab():
    """Optional opt-in fake-journal rollback by this REAL pre-Kodi unit.

    No real account/config paths are passed to the lab and OAuth feature
    flags remain OFF. No marker means NO filesystem access to lab fixtures.
    """
    if getattr(constants, "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
               False) is not True:
        return "DISABLED"
    if any(getattr(constants, name, False) is True for name in (
            "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
            "RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED",
            "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
            "RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED")):
        return "BLOCKED_REAL_RECOVERY_ENABLED"
    try:
        from tools import rclone_two_mount_reboot_journal_lab as lab
        if not os.path.lexists(lab.ROOT):
            return "NO_PENDING"
        if not early.kodi_process_absent():
            return "BLOCKED_KODI_RUNNING_OR_UNKNOWN"
        # The lab validates the earlier boot_id, exact data, permissions,
        # mountinfo and that only its own private files may be deleted.
        result = lab.verify()
        return (result if result in (
            "PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK",
            "BLOCKED_REBOOT_NOT_OBSERVED",
            "BLOCKED_INCOMPLETE_JOURNAL",
            "BLOCKED_INVALID_JOURNAL",
            "BLOCKED_LAB_PATH_MOUNTED",
            "BLOCKED_NOT_ROOT") else "MANUAL_RECOVERY_REQUIRED")
    except (OSError, ValueError, KeyError, TypeError, RuntimeError,
            UnicodeError):
        return "MANUAL_RECOVERY_REQUIRED"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--recover"]:
        print("MASQELEC_EARLY_BOOT=INVALID_MODE")
        return 0  # Kodi must never be blocked by this optional component.
    # Independent, explicitly opted-in fake data rehearsal. The real
    # migration remains gated off and cannot be authorized by this hook.
    dev_status = _dev_fake_boot_lab()
    if dev_status != "DISABLED":
        print("MASQELEC_DEV_FAKE_BOOT_LAB=" + dev_status)
    # Rollback gate and feature gates are independent of systemd installation.
    try:
        if getattr(constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                   False) is True:
            from lib import device_utils
            if client_role.allowed(device_utils.get_device_role()):
                from lib import rclone_two_mount_client_early_boot as client
                result = client.execute(authorized=True)
            else:
                result = early.execute(
                    authorized=True,
                    rollback_verified=(getattr(
                        constants, "RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED",
                        False) is True))
        else:
            result = early.execute(
                authorized=True,
                rollback_verified=(getattr(
                    constants, "RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED",
                    False) is True))
    except Exception:
        # No traceback or exception text: they might contain path/token data.
        result = "MANUAL_RECOVERY_REQUIRED"
    if result not in _ALLOWED:
        result = "MANUAL_RECOVERY_REQUIRED"
    print("MASQELEC_EARLY_BOOT=" + result)
    return 0  # Media failure must not prevent independent Kodi services.


if __name__ == "__main__":
    sys.exit(main())
