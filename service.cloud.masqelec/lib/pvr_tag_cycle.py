"""G3-O: fail-closed, opt-in TVH tag reconciliation transaction.

NOT wired into update_pvr.py. Creates a private journal BEFORE an API mutation,
and commits ownership afterwards. A journal left after process loss blocks future
writes until manually reviewed. The registry and journal are private local files.
"""
import fcntl
import json
import os
from pathlib import Path
import stat
import tempfile

from .pvr_tag_plan import plan
from .pvr_tag_reconcile import reconcile_once
from .pvr_tag_ownership import load, save, RegistryBlocked, _private_dir


class CycleBlocked(ValueError):
    pass


def _sync_dir(folder):
    fd = os.open(str(folder), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _journal_add(path, record):
    folder = _private_dir(path.parent)
    payload = json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        _sync_dir(folder)
    except BaseException:
        # Keep the journal after uncertainty: fail closed on next run.
        raise


def run_cycle(playlist, read_snapshot, post, private_dir, *,
              apply=False, allow_delete=False):
    """One action at most; dry-run is default.

    Never call with a concurrent legacy TVH tag sync. DELETE is off unless
    both apply=True and allow_delete=True; neither is enabled in production.
    """
    folder = _private_dir(Path(private_dir))
    registry = folder / "owned-tvhtags.json"
    journal = folder / "pending-tvhtag.json"
    lockpath = folder / ".tvhtag-cycle.lock"
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(str(lockpath), flags, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise CycleBlocked("LOCK_NOT_REGULAR")
        if os.fstat(fd).st_mode & 0o077:
            raise CycleBlocked("LOCK_NOT_PRIVATE")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if journal.is_symlink() or journal.exists():
            raise CycleBlocked("PENDING_OPERATION_REQUIRES_REVIEW")
        owned = load(registry)
        tags, channels = read_snapshot()
        proposed = plan(playlist, tags, channels, owned)
        if not apply:
            return {
                "status": "DRY_RUN", "creates": proposed["create_names"],
                "owned_empty_deletes": proposed["delete_owned_empty_candidates"],
                "unowned_preserved": len(proposed["preserved_unowned_or_internal_empty"]),
                "api_write_executed": False,
            }
        # Never journal/delete if there is no operation.
        operation = ("create" if proposed["create_names"] else
                     "delete" if allow_delete and proposed["delete_owned_empty_candidates"]
                     else None)
        if operation is None:
            return {"status": "UNCHANGED", "api_write_executed": False}
        target = (proposed["create_names"][0] if operation == "create"
                  else proposed["delete_owned_empty_candidates"][0])
        _journal_add(journal, {"version": 1, "operation": operation, "target": target})
        # Internal reconciler re-reads and rechecks before performing its write.
        # If the API call fails or times out, the journal remains for review.
        outcome = reconcile_once(playlist, read_snapshot, post, owned,
                                 allow_delete=allow_delete)
        if outcome["status"] not in ("CREATED", "DELETED"):
            raise CycleBlocked("EXPECTED_MUTATION_NOT_COMMITTED")
        if operation == "create" and (outcome["status"] != "CREATED" or outcome["name"] != target):
            raise CycleBlocked("CREATED_UNEXPECTED_GROUP")
        if operation == "delete" and (outcome["status"] != "DELETED" or outcome["uuid"] != target):
            raise CycleBlocked("DELETED_UNEXPECTED_GROUP")
        # Atomic ownership commit before removing pending marker.
        save(registry, outcome["owned_tag_uuids"])
        journal.unlink()
        _sync_dir(folder)
        return {"status": outcome["status"], "api_write_executed": True,
                "registry_committed": True}
    finally:
        os.close(fd)
