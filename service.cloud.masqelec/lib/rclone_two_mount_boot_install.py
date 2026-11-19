# -*- coding: utf-8 -*-
"""Install *optional* pre-Kodi recovery only for an authorized cutover.

The recovery failure never blocks Kodi: kodi.service uses Wants, not
Requires. Persistent files live in CoreELEC /storage/.config/system.d.
Never overwrite an operator's custom unit or drop-in.
"""
import os
import stat
import subprocess

from lib import rclone_two_mount_atomic_install as atomic
from lib import rclone_two_mount_startup_stage as stage

UNIT_NAME = "masqelec-v2-recovery.service"
DROPIN_NAME = "50-masqelec-v2-recovery.conf"
ADDON_SCRIPT = ("/storage/.kodi/addons/service.cloud.masqelec/tools/"
                "rclone_two_mount_early_boot_run.py")

UNIT = ("""[Unit]
Description=Optional masQelec interrupted OneDrive cutover recovery
DefaultDependencies=yes
After=local-fs.target
Before=kodi.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 """ + ADDON_SCRIPT + """
TimeoutStartSec=45
RemainAfterExit=no
""").encode("ascii")

DROPIN = b"""[Unit]
Wants=masqelec-v2-recovery.service
After=masqelec-v2-recovery.service
"""


def _existing_exact(path, expected):
    if not os.path.lexists(path):
        return False
    return stage._read_file(path)[0] == expected


def _safe_dropin_dir(path):
    info = os.lstat(path)
    if (not stat.S_ISDIR(info.st_mode) or
            info.st_uid != os.geteuid() or
            stat.S_IMODE(info.st_mode) & 0o022):
        raise ValueError("Unsafe Kodi systemd drop-in directory")

def verify_dependency(name):
    """Read merged systemd properties after daemon-reload, no pager."""
    if name != UNIT_NAME:
        return False
    try:
        result = subprocess.run(
            ["systemctl", "show", "kodi.service",
             "-p", "Wants", "-p", "After", "--no-pager"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=10, check=False)
        if result.returncode != 0:
            return False
        lines = result.stdout.decode("ascii", "strict").splitlines()
        entries = dict(line.split("=", 1) for line in lines if "=" in line)
        return (name in entries.get("Wants", "").split() and
                name in entries.get("After", "").split())
    except (OSError, subprocess.SubprocessError, UnicodeError, ValueError):
        return False


def ensure_installed(adapter, *, authorized=False, verify=None):
    """Return READY only after daemon-reload and independent verification.

    Caller must pass a verified systemctl show checker; otherwise the
    first cutover is blocked. Installation is idempotent and non-destructive.
    """
    if authorized is not True or adapter.enabled is not True:
        return "BLOCKED_BOOT_INSTALL_NOT_AUTHORIZED"
    if verify is None:
        verify = verify_dependency
    if not callable(verify) or os.geteuid() != 0:
        return "BLOCKED_BOOT_INSTALL_UNVERIFIED"
    folder = adapter.unit_dir
    unit_path = os.path.join(folder, UNIT_NAME)
    dropin_folder = os.path.join(folder, "kodi.service.d")
    dropin_path = os.path.join(dropin_folder, DROPIN_NAME)
    try:
        atomic._trusted_folder(folder)
        if not os.path.isfile(ADDON_SCRIPT) or os.path.islink(ADDON_SCRIPT):
            return "BLOCKED_BOOT_SCRIPT_MISSING"
        _safe_dropin_dir(dropin_folder) if os.path.lexists(
            dropin_folder) else None
        # Preflight all existing files before writing anything.
        for path, expected in ((unit_path, UNIT), (dropin_path, DROPIN)):
            if os.path.lexists(path) and not _existing_exact(path, expected):
                return "BLOCKED_BOOT_INSTALL_CONFLICT"
        if not os.path.lexists(unit_path):
            atomic.install_exclusive(unit_path, UNIT, 0o644)
        if not os.path.lexists(dropin_folder):
            os.mkdir(dropin_folder, 0o755)
            _safe_dropin_dir(dropin_folder)
        if not os.path.lexists(dropin_path):
            atomic.install_exclusive(dropin_path, DROPIN, 0o644)
        adapter._systemctl("daemon-reload")
        return "READY" if verify(UNIT_NAME) is True else (
            "BLOCKED_BOOT_INSTALL_UNVERIFIED")
    except (OSError, ValueError, TypeError, RuntimeError, BlockingIOError):
        return "BLOCKED_BOOT_INSTALL_FAILED"
