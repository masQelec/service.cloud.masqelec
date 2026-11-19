# -*- coding: utf-8 -*-
"""Final READ-ONLY physical cutover readiness gate for dev MASTER.

This gate cannot authorize, install, stop, or restart anything. It does
not import xbmc, read credential contents into stdout, or connect to Kodi.
It deliberately does not assert Kodi playback idle: that requires real
Kodi JSON-RPC at execution time, checked again by the cutover engine.
"""
import os
from pathlib import Path
import sys

ADDON = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ADDON))

from lib import constants
from lib import rclone_two_mount_boot_install as boot
from lib import rclone_two_mount_boot_guard as guard
from lib import rclone_two_mount_health as health
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_startup_stage as stage
from tools import rclone_two_mount_real_oauth_grouped_preflight as preflight

PARENT = stage.STAGING_PARENT
REQUIRED_FLAGS_OFF = preflight.REAL_FLAGS + (
    "RCLONE_TWO_MOUNT_DEV_FAKE_BOOT_LAB_ENABLED",
    "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
    "RCLONE_TWO_MOUNT_ROLLBACK_GATE_PASSED",
    "RCLONE_TWO_MOUNT_LEGACY_RETIRE_ENABLED",
)


def _mounted_legacy_exact():
    """Ensure each Kodi target has precisely one legacy FUSE, not a v2 bind."""
    try:
        with open("/proc/self/mountinfo", encoding="utf-8") as source:
            raw = source.read()
        entries = health.mount_entries(raw)
        targets = tuple(x[3] for x in plan.BIND_MAP)
        counts = dict.fromkeys(targets, 0)
        for line in raw.splitlines():
            columns = line.partition(" - ")[0].split()
            if len(columns) < 6:
                return False
            target = health._decode(columns[4])
            if target in counts:
                counts[target] += 1
        return (all(count == 1 for count in counts.values())
                and all(entries.get(t, {}).get("fstype") == "fuse.rclone"
                        and entries[t]["fsroot"] == "/" for t in targets)
                and all(root not in entries for root in plan.FUSE_ROOTS))
    except (OSError, ValueError, UnicodeError, TypeError):
        return False


def _staged_exact():
    """Read-only recomputation of all nine expected bytes and modes."""
    try:
        mode = rollout.mode(False)
        if mode != "legacy":
            return False
        canonical, units, _generations = stage._read_sources(
            stage.LOCAL_CONF, stage.LEGACY_UNIT_DIR)
        expected = stage._expected_artifacts(canonical[0], units)
        folder = os.path.join(PARENT, rollout.CANDIDATE_ID)
        stage._private_directory(PARENT)
        return stage._existing_matches(folder, expected)
    except (OSError, ValueError, TypeError, UnicodeError):
        return False


def _boot_order():
    """Verify both merged systemd dependencies; don't change systemd."""
    return boot.verify_dependency(boot.UNIT_NAME)


def inspect():
    output = {}
    if os.geteuid() != 0 or str(ADDON) != (
            "/storage/.kodi/addons/service.cloud.masqelec"):
        return {"CUTOVER_READINESS": "BLOCKED_DEVICE_CONTEXT"}
    if any(getattr(constants, name, False) is not False
           for name in REQUIRED_FLAGS_OFF):
        return {"CUTOVER_READINESS": "BLOCKED_FEATURE_FLAGS"}
    identity = preflight._read_role_standalone()
    output["ROLE"] = identity if identity in ("MASTER", "CLIENT") else "UNKNOWN"
    if identity != "MASTER":
        output["CUTOVER_READINESS"] = "BLOCKED_NOT_DEV_MASTER"
        return output
    output["MODE"] = rollout.mode(False)
    if output["MODE"] != "legacy":
        output["CUTOVER_READINESS"] = "BLOCKED_NOT_LEGACY"
        return output
    output["STAGING_EXACT"] = "YES" if _staged_exact() else "NO"
    output["LEGACY_MOUNTS_EXACT"] = (
        "YES" if _mounted_legacy_exact() else "NO")
    output["LEGACY_SERVICES_ACTIVE"] = (
        "YES" if all(preflight._systemd_value(u, "ActiveState") == "active"
                     for u in rollout.LEGACY_SERVICES) else "NO")
    output["BOOT_ORDER_VERIFIED"] = "YES" if _boot_order() else "NO"
    output["CLIENT_JOURNAL_PENDING"] = (
        "YES" if guard.client_recovery_pending() else "NO")
    output["CUTOVER_JOURNAL_ABSENT"] = (
        "YES" if not os.path.lexists(os.path.join(
            "/storage/.config/masqelec/rclone-v2-transaction",
            rollout.CANDIDATE_ID)) else "NO")
    output["LOCAL_STATE_MARKER_ABSENT"] = (
        "YES" if not os.path.lexists(rollout.STATE_PATH) else "NO")
    output["MEDIA_SAMPLES"] = (
        "FOUND" if _media_samples_present() else "NOT_VERIFIED")
    ready = (all(output.get(k) == "YES" for k in (
        "STAGING_EXACT", "LEGACY_MOUNTS_EXACT",
        "LEGACY_SERVICES_ACTIVE", "BOOT_ORDER_VERIFIED",
        "CUTOVER_JOURNAL_ABSENT", "LOCAL_STATE_MARKER_ABSENT"))
        and output["CLIENT_JOURNAL_PENDING"] == "NO"
        and output["MEDIA_SAMPLES"] == "FOUND")
    output["CUTOVER_READINESS"] = (
        "PASS_PREPARED_NO_ACTIVATION" if ready else
        "BLOCKED_PHYSICAL_PRECONDITIONS")
    output["KODI_IDLE_CONFIRMED"] = "NO_EXECUTION_TIME_RPC"
    output["REAL_OAUTH_VERIFIED"] = "NO"
    output["CUTOVER_EXECUTED"] = "NO"
    output["RELEASE_AUTHORIZED"] = "NO"
    return output


def _media_samples_present():
    from lib import rclone_two_mount_media_samples as media
    return media.discover() is not None


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != ["--read-only"]:
        print("CUTOVER_READINESS=BLOCKED_INVALID_MODE")
        return 2
    try:
        result = inspect()
    except (OSError, ValueError, TypeError, RuntimeError, UnicodeError,
            SyntaxError):
        result = {"CUTOVER_READINESS": "BLOCKED_UNTRUSTED_INPUT"}
    for name, value in result.items():
        print("{}={}".format(name, value))
    return 0 if result.get("CUTOVER_READINESS") == (
        "PASS_PREPARED_NO_ACTIVATION") else 2


if __name__ == "__main__":
    sys.exit(main())
