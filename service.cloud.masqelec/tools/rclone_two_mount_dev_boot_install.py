# -*- coding: utf-8 -*-
"""Explicit DEV-device install/removal of the REAL pre-Kodi recovery unit.

Unlike the release cutover, this installs only the optional recovery unit
and Kodi Wants/After drop-in, using the production boot installer. It never
changes mount units, tokens, Kodi libraries, or feature flags. The installed
runner must be the SAME (real) addon tree as this tool, and recovery flags
must remain disabled throughout this ordering-only rehearsal.
"""
import os
from pathlib import Path
import stat
import subprocess
import sys

ADDON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADDON))
from lib import constants
from lib import rclone_two_mount_atomic_install as atomic
from lib import rclone_two_mount_boot_install as boot

SYSTEMD = "/storage/.config/system.d"
LAB_FLAG = "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER"
SAFE_DISABLED = (
    "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
    "RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED",
    "RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED",
    "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
    "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
)


def _root():
    return os.geteuid() == 0


def _flags_off():
    return all(getattr(constants, name, False) is False
               for name in SAFE_DISABLED)


def _command(*args):
    try:
        result = subprocess.run(
            ["systemctl"] + list(args), timeout=20, check=False,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _expected_path():
    actual = Path(boot.ADDON_SCRIPT)
    return (str(ADDON) == str(actual.parent.parent)
            and not ADDON.is_symlink()
            and actual.is_file() and not actual.is_symlink())


def _preflight():
    if not _root():
        return "BLOCKED_NOT_ROOT"
    if not _flags_off():
        return "BLOCKED_RELEASE_FLAGS_ENABLED"
    if not _expected_path():
        return "BLOCKED_ADDON_PATH_NOT_INSTALLED"
    if not Path(boot.ADDON_SCRIPT).read_bytes().count(b"MASQELEC_EARLY_BOOT="):
        return "BLOCKED_UNEXPECTED_RUNNER"
    if not Path(SYSTEMD).is_dir() or Path(SYSTEMD).is_symlink():
        return "BLOCKED_SYSTEMD_DIRECTORY"
    try:
        atomic._trusted_folder(SYSTEMD)
        unit = Path(SYSTEMD) / boot.UNIT_NAME
        dropdir = Path(SYSTEMD) / "kodi.service.d"
        drop = dropdir / boot.DROPIN_NAME
        if dropdir.exists() or dropdir.is_symlink():
            boot._safe_dropin_dir(str(dropdir))
        if unit.exists() or unit.is_symlink():
            if not boot._existing_exact(str(unit), boot.UNIT):
                return "BLOCKED_EXISTING_UNIT_CONFLICT"
        if drop.exists() or drop.is_symlink():
            if not boot._existing_exact(str(drop), boot.DROPIN):
                return "BLOCKED_EXISTING_DROPIN_CONFLICT"
        return "READY_DISABLED_ONLY"
    except (OSError, ValueError, UnicodeError):
        return "BLOCKED_UNSAFE_FILESYSTEM"


def _install():
    check = _preflight()
    if check != "READY_DISABLED_ONLY":
        return check

    class Adapter:
        enabled = True
        unit_dir = SYSTEMD

        @staticmethod
        def _systemctl(*args):
            if not _command(*args):
                raise RuntimeError("systemctl command failed")

    outcome = boot.ensure_installed(
        Adapter(), authorized=True, verify=boot.verify_dependency)
    if outcome != "READY":
        return outcome
    return ("READY_REAL_BOOT_ORDER_INSTALLED"
            if boot.verify_dependency(boot.UNIT_NAME)
            else "BLOCKED_ORDER_VERIFICATION")


def _remove():
    check = _preflight()
    if check != "READY_DISABLED_ONLY":
        return check
    unit = Path(SYSTEMD) / boot.UNIT_NAME
    drop = Path(SYSTEMD) / "kodi.service.d" / boot.DROPIN_NAME
    if not unit.is_file() or not drop.is_file():
        return "BLOCKED_MISSING_EXPECTED_ARTIFACT"
    try:
        # Never remove operator-modified or symlinked systemd units.
        if not boot._existing_exact(str(unit), boot.UNIT):
            return "BLOCKED_EXISTING_UNIT_CONFLICT"
        if not boot._existing_exact(str(drop), boot.DROPIN):
            return "BLOCKED_EXISTING_DROPIN_CONFLICT"
        atomic.remove_if_identical(str(drop), boot.DROPIN)
        atomic.remove_if_identical(str(unit), boot.UNIT)
        if not _command("daemon-reload"):
            return "BLOCKED_RELOAD_FAILED"
        return "REMOVED_OWN_UNIT_AND_DROPIN"
    except (OSError, RuntimeError, ValueError):
        return "BLOCKED_REMOVE_FAILED"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--preflight"]:
        result = _preflight()
    elif args == ["--install-real-boot-unit", "--confirm-dev-device"]:
        result = _install()
    elif args == ["--remove-real-boot-unit", "--confirm-dev-device"]:
        result = _remove()
    else:
        result = "BLOCKED_INVALID_MODE"
    print("BOOT_DEV_DEVICE=EXPLICIT_OPERATOR_ONLY")
    print("OAUTH_OR_CREDENTIALS_CHANGED=NO")
    print("RCLONE_MOUNT_UNITS_CHANGED=NO")
    print("KODI_LIBRARY_CHANGED=NO")
    print("BOOT_DEV_RESULT=" + result)
    return 0 if result in ("READY_DISABLED_ONLY",
                           "READY_REAL_BOOT_ORDER_INSTALLED",
                           "REMOVED_OWN_UNIT_AND_DROPIN") else 2


if __name__ == "__main__":
    sys.exit(main())
