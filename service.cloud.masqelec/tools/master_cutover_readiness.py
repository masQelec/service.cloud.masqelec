# -*- coding: utf-8 -*-
"""MASTER cutover readiness checks, strictly read-only, no OAuth or Kodi calls.

This is not a cutover executable and never authorizes one.
"""
import os
import stat
import sys

UNIT_DIR = "/storage/.config/system.d"
CANONICAL = "/storage/.config/rclone/rclone.conf"
PARENT = "/storage/.config/masqelec"
TXN_PARENT = PARENT + "/rclone-v2-transaction"
ISOLATED_PARENT = "/storage/.config/rclone/isolated-mounts"
STATE = PARENT + "/rclone-mount-mode.json"
LEGACY = ("rclone_tvshows_1.service", "rclone_tvshows_2.service",
          "rclone_videos_1.service", "rclone_videos_2.service")
NEW = ("rclone_library_1.service", "rclone_library_2.service",
       "masqelec_bind_tvshows_1.service", "masqelec_bind_tvshows_2.service",
       "masqelec_bind_videos_1.service", "masqelec_bind_videos_2.service")
# Conservative threshold only; actual snapshot size is validated separately.
MIN_FREE = 16 * 1024 * 1024


def safe_dir(path, *, private=False):
    meta = os.lstat(path)
    mode = stat.S_IMODE(meta.st_mode)
    return (stat.S_ISDIR(meta.st_mode) and meta.st_uid == os.geteuid()
            and not (mode & 0o022)
            and (not private or mode == 0o700))


def checked(paths, predicate):
    return all(predicate(path) for path in paths)


def _is_root():
    return os.geteuid() == 0


def assess():
    """Return status-only flags; never expose paths or source contents."""
    report = {}
    report["ROOT"] = _is_root()
    try:
        report["UNIT_DIRECTORY_SAFE"] = safe_dir(UNIT_DIR)
    except OSError:
        report["UNIT_DIRECTORY_SAFE"] = False
    try:
        info = os.lstat(CANONICAL)
        report["CANONICAL_PRIVATE"] = (
            stat.S_ISREG(info.st_mode) and info.st_size > 0
            and not (stat.S_IMODE(info.st_mode) & 0o077))
    except OSError:
        report["CANONICAL_PRIVATE"] = False
    report["LEGACY_FILES_PRESENT"] = checked(
        LEGACY, lambda name: os.path.isfile(os.path.join(UNIT_DIR, name))
        and not os.path.islink(os.path.join(UNIT_DIR, name)))
    report["NEW_FILES_ABSENT"] = checked(
        NEW, lambda name: not os.path.lexists(os.path.join(UNIT_DIR, name)))
    report["STATE_ABSENT"] = not os.path.lexists(STATE)
    report["NO_LEGACY_DROPINS"] = checked(
        LEGACY, lambda name: not os.path.lexists(
            os.path.join(UNIT_DIR, name + ".d")))
    # Only absent/private directories are accepted; existing partial transaction
    # must be treated as unsafe rather than overwritten.
    report["NO_TRANSACTION"] = not os.path.lexists(TXN_PARENT)
    report["NO_ISOLATED_CONFIGS"] = not os.path.lexists(ISOLATED_PARENT)
    try:
        report["JOURNAL_PARENT_SAFE"] = safe_dir(PARENT, private=True)
    except OSError:
        report["JOURNAL_PARENT_SAFE"] = False
    try:
        fs = os.statvfs(PARENT)
        report["FREE_SPACE"] = fs.f_bavail * fs.f_frsize >= MIN_FREE
    except OSError:
        report["FREE_SPACE"] = False
    return report


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv != ["--read-only"]:
        print("MASTER_READINESS=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=MASTER_CUTOVER_READINESS_READ_ONLY")
    print("OAUTH_CONFIG_READ=NO")
    print("ONEDRIVE_ACCESSED=NO")
    print("SYSTEMD_OR_MOUNTS_CHANGED=NO")
    print("STRM_FILES_CHANGED=NO")
    print("MEDIA_PATHS_PRINTED=NO")
    print("KODI_PLAYBACK_IDLE=NOT_VERIFIED")
    print("CUTOVER_AUTHORIZED=NO")
    try:
        result = assess()
    except (OSError, ValueError, TypeError):
        result = {}
    fields = (
        "ROOT", "UNIT_DIRECTORY_SAFE", "CANONICAL_PRIVATE",
        "LEGACY_FILES_PRESENT", "NEW_FILES_ABSENT", "STATE_ABSENT",
        "NO_LEGACY_DROPINS", "NO_TRANSACTION", "NO_ISOLATED_CONFIGS",
        "JOURNAL_PARENT_SAFE", "FREE_SPACE",
    )
    for name in fields:
        print(name + "=" + ("PASS" if result.get(name) is True
                            else "BLOCKED"))
    passed = all(result.get(name) is True for name in fields)
    print("MASTER_READINESS=" + ("PASS_READ_ONLY" if passed
                                  else "BLOCKED_LOCAL_PREREQUISITES"))
    return 0 if passed else 2


if __name__ == "__main__":
    sys.exit(main())
