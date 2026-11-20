# -*- coding: utf-8 -*-
"""Read-only early-boot recovery inventory for MASTER; never applies rollback.

This may be run through SSH while Kodi is alive: process presence is reported,
not treated as an authorization to alter any mount or service.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib import rclone_two_mount_early_boot_recovery as early
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_rollout as rollout


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv != ["--read-only"]:
        print("EARLY_BOOT_PROBE=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=EARLY_BOOT_RECOVERY_READ_ONLY")
    print("TOKENS_READ=NO")
    print("SYSTEMD_OR_MOUNTS_CHANGED=NO")
    print("JOURNAL_WRITES=NO")
    print("RECOVERY_AUTHORIZED=NO")
    state = early.interrupted_state(live.TXN_PARENT, rollout.STATE_PATH)
    print("JOURNAL_STATE=" + state)
    proc_ok = early.kodi_process_absent()
    print("KODI_ABSENT=" + ("YES" if proc_ok else "NO_OR_UNKNOWN"))
    result = "PASS_READ_ONLY" if state in ("NO_PENDING", "ACTIVE_NO_RECOVERY") else "BLOCKED_REVIEW_REQUIRED"
    print("EARLY_BOOT_PROBE=" + result)
    return 0 if result == "PASS_READ_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())
