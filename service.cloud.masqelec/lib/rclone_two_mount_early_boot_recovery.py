# -*- coding: utf-8 -*-
"""Fail-closed early-boot recovery coordinator for KodiELEC.

No implicit installation, scheduler or enablement. A future verified systemd
unit must run this *before* Kodi starts and only on an approved release.
Do not use the Kodi JSON-RPC idle shortcut while Kodi is alive.
"""
import os
import stat

from lib import constants
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_live_adapter as live

_PROC = "/proc"
_RUNNING = frozenset(("kodi", "kodi.bin", "kodi-standalone"))


def kodi_process_absent(proc_root=_PROC):
    """False on any unreadable process inventory; no unsafe Kodi assumptions."""
    try:
        names = os.listdir(proc_root)
        for name in names:
            if not name.isdigit():
                continue
            directory = os.path.join(proc_root, name)
            try:
                with open(os.path.join(directory, "comm"), "rb") as handle:
                    comm = handle.read(128).strip().decode("ascii", "strict")
                with open(os.path.join(directory, "cmdline"), "rb") as handle:
                    argv0 = handle.read(4096).split(b"\x00", 1)[0]
                cmd = os.path.basename(argv0.decode("utf-8", "strict"))
            except FileNotFoundError:
                # A short-lived process disappeared during the scan.
                continue
            except (OSError, UnicodeError):
                return False
            if comm in _RUNNING or cmd in _RUNNING:
                return False
        return True
    except (OSError, UnicodeError):
        return False


def interrupted_state(parent, state_path):
    """Only an exactly journaled interrupted transaction may be restored."""
    txn = os.path.join(parent, rollout.CANDIDATE_ID)
    try:
        present = os.path.lexists(txn)
        marker = os.path.lexists(state_path)
        if not present and not marker:
            return "NO_PENDING"
        if not present or not marker:
            return "BLOCKED_INCONSISTENT_STATE"
        phase = journal.phase(txn)
        if phase in ("cutover_started", "rollback_required"):
            # The state marker may not be ACTIVE; that would indicate a
            # torn mark_active operation requiring explicit intervention.
            if rollout.mode(True, state_path=state_path) != "unsafe":
                return "BLOCKED_INCONSISTENT_STATE"
            return "INTERRUPTED"
        if phase == "prepared":
            return "BLOCKED_INCONSISTENT_STATE"
        if phase == "active":
            return "ACTIVE_NO_RECOVERY"
        return "BLOCKED_INCONSISTENT_STATE"
    except (OSError, ValueError, TypeError, UnicodeError):
        return "BLOCKED_INCONSISTENT_STATE"


def execute(*, authorized=False, rollback_verified=False, proc_root=_PROC,
            adapter_factory=None, txn_parent=live.TXN_PARENT,
            state_path=rollout.STATE_PATH):
    """Recover only under early-boot authorization; never read/write STRM."""
    if authorized is not True or rollback_verified is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if (getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True):
        return "BLOCKED_FEATURE_DISABLED"
    if os.geteuid() != 0:
        return "BLOCKED_NOT_ROOT"
    state = interrupted_state(txn_parent, state_path)
    if state != "INTERRUPTED":
        return state
    if not kodi_process_absent(proc_root):
        return "BLOCKED_KODI_RUNNING_OR_UNKNOWN"
    # This callback is valid ONLY while Kodi is verifiably absent at boot.
    # LocalAdapter.recover_pending_from_disk checks idle and reconciles
    # private account tokens under journal.locked before restoring legacy.
    idle_rpc = lambda _request: '{"jsonrpc":"2.0","id":1,"result":[]}'
    maker = adapter_factory or live.LocalAdapter
    try:
        adapter = maker(rpc_call=idle_rpc, live_enabled=True,
                        txn_parent=txn_parent, state_path=state_path,
                        known_media_files=())
        with journal.locked(adapter.txn_parent):
            # Recheck under lock immediately before mutable actions.
            if not kodi_process_absent(proc_root):
                return "BLOCKED_KODI_RUNNING_OR_UNKNOWN"
            if interrupted_state(txn_parent, state_path) != "INTERRUPTED":
                return "BLOCKED_STATE_CHANGED"
            result = adapter.recover_pending_from_disk()
        return result if result == "ROLLED_BACK" else "MANUAL_RECOVERY_REQUIRED"
    except (OSError, ValueError, RuntimeError, TypeError, BlockingIOError):
        return "MANUAL_RECOVERY_REQUIRED"
