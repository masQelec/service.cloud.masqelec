# -*- coding: utf-8 -*-
"""Systemd early-boot runner: recovery failure is nonfatal for KodiELEC.

Only an explicitly authorized release can mutate mounts. A nonzero Kodi
startup dependency is intentionally avoided: media is optional.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import constants
from lib import rclone_two_mount_early_boot_recovery as early

_ALLOWED = frozenset({
    "NO_PENDING", "ACTIVE_NO_RECOVERY", "ROLLED_BACK",
    "BLOCKED_NOT_AUTHORIZED", "BLOCKED_FEATURE_DISABLED",
    "BLOCKED_NOT_ROOT", "BLOCKED_INCONSISTENT_STATE",
    "BLOCKED_KODI_RUNNING_OR_UNKNOWN", "BLOCKED_STATE_CHANGED",
    "MANUAL_RECOVERY_REQUIRED",
})


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--recover"]:
        print("MASQELEC_EARLY_BOOT=INVALID_MODE")
        return 0  # Kodi must never be blocked by this optional component.
    # Rollback gate and feature gates are independent of systemd installation.
    result = early.execute(
        authorized=True,
        rollback_verified=(getattr(
            constants, "RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED", False)
            is True),
    )
    if result not in _ALLOWED:
        result = "MANUAL_RECOVERY_REQUIRED"
    print("MASQELEC_EARLY_BOOT=" + result)
    return 0  # Media failure must not prevent independent Kodi services.


if __name__ == "__main__":
    sys.exit(main())
