# -*- coding: utf-8 -*-
"""Two-phase REAL REBOOT durability probe of an ISOLATED fake OAuth journal.

NO rclone, OAuth, systemd, network, Kodi or production account paths touched.
The only persistent footprint is a private, fixed-purpose directory under
/storage/.config. Prepare never reboots the device. Verification requires a
different kernel boot_id, validates exact fake bytes, performs fsynced rollback
and cleans only this lab's allowlisted files and folder. Idempotent *blocking*
on unexpected/corrupt state: never erase unknown user data.

This is NOT a production early-boot ordering or OAuth integration test.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

ROOT = Path("/storage/.config/masqelec-v2-reboot-journal-lab")
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
ORIGINAL = b"MASQELEC_LAB_FAKE_OAUTH_BASELINE_v1\n"
CANDIDATE = b"MASQELEC_LAB_FAKE_OAUTH_CANDIDATE_v1\n"
OTHER = b"MASQELEC_LAB_SECOND_ACCOUNT_UNCHANGED_v1\n"
STATE = "state.json"
FILES = frozenset((STATE, "account1.conf", "account1.bak", "account2.conf"))
ENTRIES = frozenset((STATE, "account1.conf", "account1.bak", "account2.conf"))
MAX_STATE = 1024


def _boot_id():
    value = BOOT_ID.read_text(encoding="ascii").strip()
    if len(value) != 36 or any(c not in "0123456789abcdef-" for c in value):
        raise ValueError("Invalid Linux boot identity")
    return value


def _check_parent():
    parent = ROOT.parent
    meta = os.lstat(parent)
    if (not stat.S_ISDIR(meta.st_mode) or os.path.islink(parent)
            or os.path.realpath(str(parent)) != str(parent)):
        raise ValueError("Unsafe lab parent")


def _private_dir():
    info = os.lstat(ROOT)
    if (not stat.S_ISDIR(info.st_mode) or
            stat.S_IMODE(info.st_mode) != 0o700 or
            info.st_uid != os.geteuid()):
        raise ValueError("Unsafe lab directory")
    entries = set(os.listdir(ROOT))
    if entries - ENTRIES:
        raise ValueError("Unexpected lab entries")
    return entries


def _sync_dir():
    fd = os.open(str(ROOT), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_exact(name, expected=None):
    path = ROOT / name
    meta = os.lstat(path)
    if (not stat.S_ISREG(meta.st_mode) or
            stat.S_IMODE(meta.st_mode) != 0o600 or
            meta.st_uid != os.geteuid() or
            not 0 < meta.st_size <= MAX_STATE):
        raise ValueError("Untrusted lab file")
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        data = os.read(fd, MAX_STATE + 1)
    finally:
        os.close(fd)
    if expected is not None and data != expected:
        raise ValueError("Unexpected fake fixture bytes")
    return data


def _create(name, payload):
    fd = os.open(str(ROOT / name), os.O_WRONLY | os.O_CREAT |
                 os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as output:
            output.write(payload)
            output.flush()
        os.fsync(fd)
    finally:
        os.close(fd)
    _sync_dir()


def _atomic(name, payload):
    temp = ROOT / ".atomic"
    if os.path.lexists(temp):
        raise ValueError("Unknown incomplete write")
    fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as output:
            output.write(payload)
            output.flush()
        os.fsync(fd)
        os.replace(str(temp), str(ROOT / name))
        _sync_dir()
    finally:
        os.close(fd)


def _serialize(phase, boot):
    return json.dumps({
        "version": 1, "lab": "MASQELEC_ISOLATED_REBOOT_JOURNAL",
        "phase": phase, "prepare_boot": boot,
        "baseline_sha256": hashlib.sha256(ORIGINAL).hexdigest(),
        "other_sha256": hashlib.sha256(OTHER).hexdigest(),
    }, sort_keys=True).encode("ascii")


def _mounts_clear():
    prefix = str(ROOT)
    with open("/proc/self/mountinfo", "r", encoding="utf-8") as source:
        for row in source:
            a = row.partition(" - ")[0].split()
            if len(a) < 5:
                raise ValueError("Malformed mountinfo")
            mount = a[4].replace("\\040", " ")
            if mount == prefix or mount.startswith(prefix + "/"):
                return False
    return True


def prepare():
    _check_parent()
    if os.path.lexists(ROOT):
        return "BLOCKED_EXISTING_LAB"
    if os.geteuid() != 0:
        return "BLOCKED_NOT_ROOT"
    boot = _boot_id()
    ROOT.mkdir(mode=0o700)
    _sync_dir()
    _create("account1.conf", ORIGINAL)
    _create("account1.bak", ORIGINAL)
    _create("account2.conf", OTHER)
    _create(STATE, _serialize("prepared", boot))
    _atomic("account1.conf", CANDIDATE)
    _atomic(STATE, _serialize("install_requested", boot))
    if not _mounts_clear() or _read_exact("account1.conf", CANDIDATE) != CANDIDATE:
        raise ValueError("Unsafe lab setup")
    _read_exact("account1.bak", ORIGINAL)
    _read_exact("account2.conf", OTHER)
    return "PREPARED_REBOOT_REQUIRED"


def verify():
    _check_parent()
    if os.geteuid() != 0:
        return "BLOCKED_NOT_ROOT"
    if not os.path.lexists(ROOT):
        return "BLOCKED_NO_PREPARED_LAB"
    entries = _private_dir()
    if entries != ENTRIES:
        return "BLOCKED_INCOMPLETE_JOURNAL"
    state = json.loads(_read_exact(STATE))
    expected = json.loads(_serialize("install_requested",
                                     state.get("prepare_boot", "")))
    if state != expected:
        return "BLOCKED_INVALID_JOURNAL"
    if state["prepare_boot"] == _boot_id():
        return "BLOCKED_REBOOT_NOT_OBSERVED"
    if not _mounts_clear():
        return "BLOCKED_LAB_PATH_MOUNTED"
    _read_exact("account1.conf", CANDIDATE)
    _read_exact("account1.bak", ORIGINAL)
    _read_exact("account2.conf", OTHER)
    # Rollback of fake bytes only, after an actual kernel boot_id change.
    _atomic("account1.conf", ORIGINAL)
    _atomic(STATE, _serialize("rolled_back", state["prepare_boot"]))
    _read_exact("account1.conf", ORIGINAL)
    _read_exact("account2.conf", OTHER)
    # Clean only the exact allowlist, never an unknown file or directory.
    _private_dir()
    for name in ("account1.bak", "account1.conf", "account2.conf", STATE):
        os.unlink(str(ROOT / name))
        _sync_dir()
    os.rmdir(str(ROOT))
    return "PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK"


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (["--prepare", "--confirm-isolated-only"],
                    ["--verify-after-reboot", "--confirm-isolated-only"]):
        print("REBOOT_LAB_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("REBOOT_LAB_MODE=ISOLATED_FAKE_OAUTH_PERSISTENCE")
    print("REAL_OAUTH_ACCESSED=NO")
    print("SYSTEMD_UNITS_CHANGED=NO")
    print("KODI_MOUNTS_CHANGED=NO")
    print("REBOOT_TRIGGERED=NO")
    try:
        result = prepare() if args[0] == "--prepare" else verify()
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        result = "BLOCKED_UNSAFE_OR_INCOMPLETE_LAB"
    print("REBOOT_LAB_RESULT=" + result)
    return 0 if result in (
        "PREPARED_REBOOT_REQUIRED",
        "PASS_REAL_REBOOT_FAKE_JOURNAL_ROLLBACK") else 2


if __name__ == "__main__":
    sys.exit(main())
