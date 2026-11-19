# -*- coding: utf-8 -*-
"""Grouped, read-only preflight for the v2 MASTER-as-CLIENT OAuth pilot.

No credential bytes, network, Kodi RPC, mount modifications or systemd writes.
This command CANNOT authorize a migration or OAuth recovery.
"""
import ast
import glob
import os
from pathlib import Path
import stat
import subprocess
import sys

ADDON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADDON))
from lib import constants
from lib import rclone_two_mount_boot_guard as guard
from lib import rclone_two_mount_config_routes as routes
from lib import rclone_two_mount_health as health
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout

UNIT = "masqelec-v2-recovery.service"
REAL_FLAGS = (
    "RCLONE_TOKEN_SYNC_ENABLED",
    "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
    "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
    "RCLONE_TWO_MOUNT_FIRST_RUN_ENABLED",
    "RCLONE_TWO_MOUNT_AUTO_RECOVERY_ENABLED",
    "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
)
UNITS = rollout.NEW_SERVICES + rollout.BIND_SERVICES


def _regular_private(path):
    try:
        meta = os.lstat(path)
        return (stat.S_ISREG(meta.st_mode) and
                stat.S_IMODE(meta.st_mode) == 0o600 and
                meta.st_uid == os.geteuid() and
                0 < meta.st_size <= 1024 * 1024)
    except OSError:
        return False


def _systemd_value(unit, prop):
    try:
        completed = subprocess.run(
            ["systemctl", "show", unit, "-p", prop, "--value"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=8, check=False, text=True)
        if completed.returncode != 0:
            return "unknown"
        return completed.stdout.strip().splitlines()[0].strip() or "unknown"
    except (OSError, subprocess.SubprocessError, IndexError):
        return "unknown"


def _mount_topology():
    """Return raw mountpoint inventory plus independently verified v2 layout."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as stream:
            raw = stream.read()
        entries = health.mount_entries(raw)
        return set(entries), health.check_two_fuse_four_bind(raw)
    except (OSError, ValueError, TypeError, UnicodeError):
        return None, False


def _literal_master_identity():
    """Read exact current constants from device_utils WITHOUT importing Kodi."""
    path = ADDON / "lib" / "device_utils.py"
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 65536:
        raise ValueError("Unsafe role definition")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    values = {}
    wanted = ("DEFAULT_MASTER_ETH0_MACS",
              "DEFAULT_MASTER_NODE_NAME_ZEROTIER")
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    if not isinstance(node.value, ast.Constant) or not isinstance(
                            node.value.value, str):
                        raise ValueError("Nonliteral device identity")
                    values[target.id] = node.value.value
    if set(values) != set(wanted):
        raise ValueError("Missing role definition")
    return (values[wanted[0]], values[wanted[1]])


def _read_role_standalone():
    """Equivalent positive MASTER attestation without xbmcvfs/Kodi imports.

    Missing identity data blocks the pilot instead of being treated as CLIENT.
    """
    macs, expected_name = _literal_master_identity()
    if not expected_name.strip():
        return "UNKNOWN"
    mac_path = Path("/sys/class/net/eth0/address")
    eth0 = mac_path.read_text(encoding="ascii").strip().lower().replace(
        ":", "").replace("-", "")
    allowed = set()
    for candidate in macs.replace(",", " ").split():
        normalized = candidate.strip().lower().replace(
            ":", "").replace("-", "")
        if len(normalized) == 12 and all(c in "0123456789abcdef"
                                          for c in normalized):
            allowed.add(normalized)
    if len(eth0) != 12 or not all(c in "0123456789abcdef" for c in eth0):
        return "UNKNOWN"
    if eth0 not in allowed:
        return "CLIENT"
    zt_dirs = (
        "/opt/var/lib/zerotier-one/networks.d",
        "/var/lib/zerotier-one/networks.d",
        "/storage/.cache/zerotier-one/networks.d",
    )
    for dirname in zt_dirs:
        if not os.path.isdir(dirname):
            continue
        config_files = [
            p for p in glob.glob(os.path.join(dirname, "*.conf"))
            if not p.endswith(".local.conf")]
        if not config_files:
            return "UNKNOWN"
        latest = max(config_files, key=os.path.getmtime)
        if os.path.islink(latest) or os.path.getsize(latest) > 65536:
            return "UNKNOWN"
        node_name = None
        with open(latest, "rb") as source:
            for raw in source:
                line = raw.strip()
                if line.startswith((b"C=", b"COO=")):
                    break
                if line.startswith(b"n="):
                    node_name = line[2:].decode("utf-8", "strict").strip()
        return "MASTER" if node_name == expected_name else "CLIENT" if node_name else "UNKNOWN"
    return "UNKNOWN"


def inspect(role=None):
    """Closed, non-secret statuses; never calls GitHub, OneDrive or rclone."""
    output = {}
    if os.geteuid() != 0:
        return {"PILOT_GATE": "BLOCKED_NOT_ROOT"}
    if str(ADDON) != "/storage/.kodi/addons/service.cloud.masqelec":
        return {"PILOT_GATE": "BLOCKED_NOT_INSTALLED_ADDON"}
    if constants.CLOUD_BRANCH != "develop":
        return {"PILOT_GATE": "BLOCKED_BRANCH"}
    if not all(getattr(constants, name, False) is False for name in REAL_FLAGS):
        return {"PILOT_GATE": "BLOCKED_REAL_FEATURE_FLAGS_ENABLED"}
    if getattr(constants, "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
               False) is not False:
        return {"PILOT_GATE": "BLOCKED_FAKE_LAB_ENABLED"}
    if os.path.lexists("/storage/.config/masqelec-v2-reboot-journal-lab"):
        return {"PILOT_GATE": "BLOCKED_FAKE_LAB_REMAINS"}
    if role is None:
        try:
            role = _read_role_standalone()
        except (OSError, ValueError, RuntimeError, UnicodeError,
                SyntaxError, TypeError):
            return {"PILOT_GATE": "BLOCKED_ROLE_UNAVAILABLE"}
    output["DEVICE_ROLE"] = role if role in ("MASTER", "CLIENT") else "UNKNOWN"
    if role != "MASTER":
        output["PILOT_GATE"] = "BLOCKED_NOT_DEV_MASTER"
        return output
    # Scoped role override must remain disabled before an explicit live pilot.
    output["DEV_CLIENT_OVERRIDE"] = (
        "ON" if getattr(constants,
                        "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
                        False) is True else "OFF")
    output["MODE"] = rollout.mode(True)
    output["LOCAL_CONFIG"] = ("PRIVATE" if _regular_private(
        "/storage/.config/rclone/rclone.conf") else "MISSING_OR_UNSAFE")
    output["ACCOUNT1_CONFIG"] = ("PRIVATE" if _regular_private(
        plan.ACCOUNT_CONFS[0]) else "MISSING_OR_UNSAFE")
    output["ACCOUNT2_CONFIG"] = ("PRIVATE" if _regular_private(
        plan.ACCOUNT_CONFS[1]) else "MISSING_OR_UNSAFE")
    output["CLIENT_JOURNAL_PENDING"] = (
        "YES" if guard.client_recovery_pending() else "NO")
    output["MQC2_V2_ROUTE"] = routes.V2_REMOTE_PATH
    output["EARLY_BOOT_UNIT"] = _systemd_value(UNIT, "LoadState")
    mounts, topology_verified = _mount_topology()
    output["V2_MOUNT_TOPOLOGY"] = (
        "VERIFIED" if topology_verified else "NOT_VERIFIED")
    for index, unit in enumerate(UNITS):
        output["UNIT_{}".format(index + 1)] = (
            _systemd_value(unit, "ActiveState"))
    for index, target in enumerate(plan.FUSE_ROOTS):
        output["FUSE_{}".format(index + 1)] = (
            "UNKNOWN" if mounts is None else
            "MOUNTED" if target in mounts else "NOT_MOUNTED")
    for index, bind in enumerate(plan.BIND_MAP):
        target = bind[3]
        output["BIND_{}".format(index + 1)] = (
            "VERIFIED_V2_BIND" if topology_verified else
            "UNKNOWN" if mounts is None else
            "LEGACY_OR_UNVERIFIED" if target in mounts else "NOT_MOUNTED")
    active_ready = (
        output["MODE"] == "active"
        and all(output["UNIT_{}".format(i)] == "active"
                for i in range(1, 7))
        and topology_verified
        and all(output["FUSE_{}".format(i)] == "MOUNTED"
                for i in range(1, 3))
        and all(output["BIND_{}".format(i)] == "VERIFIED_V2_BIND"
                for i in range(1, 5))
        and output["ACCOUNT1_CONFIG"] == "PRIVATE"
        and output["ACCOUNT2_CONFIG"] == "PRIVATE"
        and output["CLIENT_JOURNAL_PENDING"] == "NO")
    output["PILOT_GATE"] = (
        "READONLY_ACTIVE_LAYOUT_PRESENT_NEEDS_OAUTH_GATES"
        if active_ready else "BLOCKED_V2_LAYOUT_NOT_VERIFIED")
    return output


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["--read-only"]:
        print("PILOT_GATE=BLOCKED_INVALID_MODE")
        return 2
    result = inspect()
    for key, value in result.items():
        print("{}={}".format(key, value))
    return 0 if result.get("PILOT_GATE") == (
        "READONLY_ACTIVE_LAYOUT_PRESENT_NEEDS_OAUTH_GATES") else 2


if __name__ == "__main__":
    sys.exit(main())
