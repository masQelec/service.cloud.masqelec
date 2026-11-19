# -*- coding: utf-8 -*-
"""Durable per-account CLIENT v2 OAuth recovery file adapter.

Real disk writes, but **no built-in systemd or OAuth calls**. By default the
transaction is disabled. The caller supplies exact-account stop/start/health
callbacks and a pre-validated private root; do not use for live deployments
before proving the mount writer fence and crash recovery on KodiELEC.
"""
import fcntl
import json
import os
import stat
import tempfile
from contextlib import contextmanager

from lib import rclone_two_mount_startup_stage as stage


def _dir(path):
    info = os.lstat(path)
    if (not stat.S_ISDIR(info.st_mode) or
            info.st_uid != os.geteuid() or
            stat.S_IMODE(info.st_mode) != 0o700):
        raise ValueError("Untrusted private recovery folder")


def _sync(folder):
    fd = os.open(folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, content):
    if not isinstance(content, bytes) or not 0 < len(content) <= 1024 * 1024:
        raise ValueError("Invalid private content")
    folder = os.path.dirname(path)
    _dir(folder)
    fd, tmp = tempfile.mkstemp(prefix=".oauth-txn-", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as out:
            out.write(content)
            out.flush()
        os.fsync(fd)
        os.replace(tmp, path)
        _sync(folder)
    finally:
        os.close(fd)
        if os.path.lexists(tmp):
            os.unlink(tmp)


def _read(path):
    content, generation = stage._read_file(path, confidential=True)
    meta = os.lstat(path)
    if (meta.st_uid != os.geteuid() or
            stat.S_IMODE(meta.st_mode) != 0o600):
        raise ValueError("Untrusted account config")
    return content, generation


def provision_private_journal(folder):
    """Create only a private account journal under an existing trusted base.

    The base /storage/.config/masqelec must already exist at 0700 and be
    owned by this user; never mkdir parents recursively or follow symlinks.
    Only used by the explicitly enabled apply path.
    """
    if os.path.basename(folder) not in ("account1", "account2"):
        raise ValueError("Unexpected CLIENT journal name")
    parent = os.path.dirname(folder)
    ancestor = os.path.dirname(parent)
    _dir(ancestor)
    if not os.path.lexists(parent):
        os.mkdir(parent, 0o700)
        _sync(ancestor)
    _dir(parent)
    if not os.path.lexists(folder):
        os.mkdir(folder, 0o700)
        _sync(parent)
    _dir(folder)
    return True


@contextmanager
def locked(folder):
    """Exclusive local lock; caller holds it throughout transaction."""
    _dir(folder)
    path = os.path.join(folder, ".lock")
    fd = os.open(path, os.O_CREAT | os.O_RDWR |
                 getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or
                stat.S_IMODE(info.st_mode) != 0o600 or
                info.st_uid != os.geteuid()):
            raise ValueError("Unsafe lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _state_path(folder):
    return os.path.join(folder, "state.json")


def recovery_pending(folder, account_index=None):
    """Fail closed on incomplete/corrupt state, never autorestart writers."""
    if not os.path.lexists(folder):
        return False
    try:
        _dir(folder)
        path = _state_path(folder)
        if not os.path.lexists(path):
            return any(x.startswith("account") and x.endswith(".bak")
                       for x in os.listdir(folder))
        raw, _ = _read(path)
        state = json.loads(raw)
        return (type(state) is not dict or
                set(state) != {"version", "account", "phase"} or
                state.get("version") != 1 or
                type(state.get("account")) is not int or
                state["account"] not in (0, 1) or
                (account_index is not None and state["account"] != account_index) or
                state.get("phase") not in ("committed", "rolled_back"))
    except (OSError, ValueError, TypeError, UnicodeError):
        return True


def retire_finalized(folder, index):
    """Retire a *completed* prior journal under locked(folder).

    Crash-safe because no active transaction exists in these two phases.
    An incomplete/corrupt state or unexpected entry is NEVER discarded.
    Remove prior backup first, state last, syncing directory each time.
    """
    _dir(folder)
    path = _state_path(folder)
    if not os.path.lexists(path):
        return False
    raw, _ = _read(path)
    obj = json.loads(raw)
    if (type(obj) is not dict or
            set(obj) != {"version", "account", "phase"} or
            obj["version"] != 1 or type(obj["account"]) is not int or
            obj["account"] != index or
            obj["phase"] not in ("committed", "rolled_back")):
        return False
    name = "account{}.bak".format(index + 1)
    allowed = {".lock", "state.json", name}
    if set(os.listdir(folder)) - allowed:
        return False
    backup = os.path.join(folder, name)
    if os.path.lexists(backup):
        _read(backup)  # confirm mode, owner, regular file, no symlink
        os.unlink(backup)
        _sync(folder)
    os.unlink(path)
    _sync(folder)
    return True


class AccountFileOps:
    """Concrete durable file operations + explicit service callbacks.

    One instance handles exactly one account; other config is never opened.
    The caller MUST hold locked(journal_dir) around transaction.execute.
    Callback signatures: stop(index), quiescent(index), start(index),
    healthy(index). Their implementation must verify FUSE and two binds.
    """
    def __init__(self, index, *, account_path, journal_dir,
                 stop, quiescent, start, healthy, enabled=False):
        if type(index) is not int or index not in (0, 1):
            raise ValueError("Invalid account")
        if os.path.basename(account_path) != "account{}.conf".format(index + 1):
            raise ValueError("Account config name mismatched")
        if os.path.islink(account_path) or os.path.islink(journal_dir):
            raise ValueError("Symlinks not allowed")
        self.index = index
        self.account_path = account_path
        self.journal_dir = journal_dir
        self.enabled = enabled is True
        self._stop, self._quiescent = stop, quiescent
        self._start, self._healthy = start, healthy
        self._generation = None
        self._baseline = None

    def _require(self, index):
        if not self.enabled or type(index) is not int or index != self.index:
            raise PermissionError("Account file operations not enabled")
        _dir(os.path.dirname(self.account_path))
        _dir(self.journal_dir)

    def _phase(self, phase):
        _atomic(_state_path(self.journal_dir), json.dumps({
            "version": 1, "account": self.index, "phase": phase
        }, sort_keys=True).encode("ascii"))

    def snapshot(self, index, expected):
        self._require(index)
        if recovery_pending(self.journal_dir, index):
            return False
        raw, gen = _read(self.account_path)
        if raw != expected:
            return False
        # A completed earlier transaction cannot permanently prevent later
        # OAuth token rotations. Under the same exclusive lock, safely
        # retire it; never discard an incomplete/unknown journal.
        if os.path.lexists(_state_path(self.journal_dir)):
            if not retire_finalized(self.journal_dir, index):
                return False
        backup = os.path.join(self.journal_dir,
                              "account{}.bak".format(index + 1))
        if os.path.lexists(backup):
            return False
        fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as out:
                out.write(raw)
                out.flush()
            os.fsync(fd)
        finally:
            os.close(fd)
        _sync(self.journal_dir)
        self._baseline, self._generation = raw, gen
        self._phase("prepared")
        return True

    def stop(self, index):
        self._require(index)
        self._phase("stop_requested")
        return self._stop(index) is True

    def quiescent(self, index):
        self._require(index)
        return self._quiescent(index) is True

    def still_current(self, index, expected):
        self._require(index)
        raw, gen = _read(self.account_path)
        return raw == expected and gen == self._generation

    def install(self, index, candidate):
        self._require(index)
        if self._quiescent(index) is not True:
            return False
        if not self.still_current(index, self._baseline):
            return False
        self._phase("install_requested")
        _atomic(self.account_path, candidate)
        return _read(self.account_path)[0] == candidate

    def start(self, index):
        self._require(index)
        self._phase("start_requested")
        return self._start(index) is True

    def healthy(self, index):
        self._require(index)
        return self._healthy(index) is True

    def commit(self, index):
        self._require(index)
        self._phase("committed")
        return True

    def rollback(self, index):
        self._require(index)
        # Require independent stop/quiescence even after partially failed stop.
        self._phase("rollback_requested")
        if self._stop(index) is not True or self._quiescent(index) is not True:
            return False
        backup = os.path.join(self.journal_dir,
                              "account{}.bak".format(index + 1))
        prior, _ = _read(backup)
        if prior != self._baseline:
            return False
        _atomic(self.account_path, prior)
        if self._start(index) is not True:
            return False
        return True

    def rollback_healthy(self, index):
        self._require(index)
        if (self._healthy(index) is not True or
                _read(self.account_path)[0] != self._baseline):
            return False
        self._phase("rolled_back")
        return True
