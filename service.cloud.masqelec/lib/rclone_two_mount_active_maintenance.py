# -*- coding: utf-8 -*-
"""Idempotent v2 mount supervision after a completed local cutover.

Never stop a running mount, replace OAuth, recreate legacy, or start one
service on top of an occupied mount path. Kodi keeps working on failure.
"""
import os

from lib import rclone_two_mount_atomic_install as atomic
from lib import rclone_two_mount_health as health
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_startup_stage as stage


def _safe_artifacts(adapter):
    atomic._trusted_folder(adapter.unit_dir)
    for name in rollout.NEW_SERVICES + rollout.BIND_SERVICES:
        stage._read_file(os.path.join(adapter.unit_dir, name))
    for path in adapter.account_confs:
        stage._read_file(path, confidential=True)


def ensure_active(adapter, *, authorized=False):
    """Start only missing units; never manipulate healthy units.

    A stopped unit with a mounted target is ambiguous, so fail closed.
    The caller can log the status and continue Kodi startup unchanged.
    """
    if authorized is not True or adapter.enabled is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    try:
        with journal.locked(adapter.txn_parent):
            if rollout.mode(True, state_path=adapter.state_path) != "active":
                return "BLOCKED_NOT_ACTIVE"
            target = os.path.join(adapter.txn_parent, rollout.CANDIDATE_ID)
            if journal.phase(target) != "active":
                return "BLOCKED_JOURNAL_NOT_ACTIVE"
            _safe_artifacts(adapter)
            # Never start v2 if any legacy service still runs.
            if any(adapter._active(unit) for unit in rollout.LEGACY_SERVICES):
                return "BLOCKED_LEGACY_RUNNING"
            before = adapter._mounts()
            # The legacy FUSE superblock has root=/ on its Kodi target.
            for _name, _idx, _folder, destination in plan.BIND_MAP:
                old = before.get(destination)
                if old and old["fstype"] == "fuse.rclone" and old["fsroot"] == "/":
                    return "BLOCKED_LEGACY_MOUNT"
            changed = False
            for unit, root in zip(rollout.NEW_SERVICES, plan.FUSE_ROOTS):
                running = adapter._active(unit)
                mounted = root in adapter._mounts()
                if running:
                    if not mounted:
                        return "BLOCKED_ROOT_ACTIVE_UNMOUNTED"
                elif mounted:
                    return "BLOCKED_ROOT_OCCUPIED"
                else:
                    adapter._systemctl("start", unit)
                    changed = True
            entries = adapter._mounts()
            if not all(entries.get(root, {}).get("fstype") == "fuse.rclone"
                       for root in plan.FUSE_ROOTS):
                return "BLOCKED_ROOT_NOT_READY"
            for unit, (_name, _idx, _folder, destination) in zip(
                    rollout.BIND_SERVICES, plan.BIND_MAP):
                running = adapter._active(unit)
                mounted = destination in adapter._mounts()
                if running:
                    if not mounted:
                        return "BLOCKED_BIND_ACTIVE_UNMOUNTED"
                elif mounted:
                    return "BLOCKED_BIND_OCCUPIED"
                else:
                    adapter._systemctl("start", unit)
                    changed = True
            if not health.check_two_fuse_four_bind(adapter.mount_reader()):
                return "BLOCKED_V2_UNHEALTHY"
            return "ACTIVE_REPAIRED" if changed else "ACTIVE_HEALTHY"
    except (OSError, ValueError, TypeError, KeyError, RuntimeError,
            BlockingIOError):
        return "BLOCKED_ACTIVE_MAINTENANCE"
