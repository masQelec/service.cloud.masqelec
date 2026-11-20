# -*- coding: utf-8 -*-
"""CLIENT v2 systemd adapter, exclusively for one selected account.

No effects at import time; ALL actions require enabled=True. This adapter
does not authorize live rollout, manage credentials, or discover OAuth auth
failures. Its callbacks can be passed to AccountFileOps only after the
operator has approved a physical cutover and verified crash recovery.
"""
import os
import subprocess
import time

from lib import rclone_two_mount_health as health
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout


def account_units(index):
    if type(index) is not int or index not in (0, 1):
        raise ValueError("Invalid account index")
    binds = tuple(item[0] for item in plan.BIND_MAP if item[1] == index)
    if len(binds) != 2:
        raise ValueError("Unexpected bind inventory")
    return rollout.NEW_SERVICES[index], binds


def _run(args):
    try:
        return subprocess.run(args, check=False, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=50).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _mountinfo():
    with open("/proc/self/mountinfo", "r", encoding="utf-8") as stream:
        return stream.read()


def _writer_present(config_path):
    """Fail closed on inaccessible /proc or unknown rclone mount config."""
    target = os.path.realpath(config_path)
    try:
        with os.scandir("/proc") as procs:
            for process in procs:
                if not process.name.isdigit() or int(process.name) == os.getpid():
                    continue
                try:
                    with open(os.path.join(process.path, "cmdline"), "rb") as fd:
                        args = [x.decode("utf-8", "replace") for x in
                                fd.read(16384).split(b"\x00") if x]
                except (FileNotFoundError, ProcessLookupError):
                    continue
                except OSError:
                    return True
                if not args or not os.path.basename(args[0]).startswith("rclone"):
                    continue
                if "mount" not in args[1:10]:
                    continue
                conf = None
                for n, arg in enumerate(args[1:], 1):
                    if arg == "--config" and n+1 < len(args):
                        conf = args[n+1]
                        break
                    if arg.startswith("--config="):
                        conf = arg.split("=", 1)[1]
                        break
                if conf is None or os.path.realpath(conf) == target:
                    return True
        return False
    except OSError:
        return True


class AccountSystemd:
    """Explicitly gated systemd callbacks for AccountFileOps.

    No 'restart': bind stops precede root stop; root start precedes bind
    starts. Mountinfo must show one matching FUSE and both matching binds,
    with no stacked paths. Required media_check(i) must read known media.
    """
    def __init__(self, index, *, enabled=False, run=None,
                 mountinfo=None, writer_present=None, media_check=None,
                 wait=None, retries=30):
        self.index = index
        self.root_unit, self.bind_units = account_units(index)
        self.enabled = enabled is True
        self.run = run if run is not None else _run
        self.mountinfo = mountinfo if mountinfo is not None else _mountinfo
        self.writer_present = (writer_present if writer_present is not None
                               else _writer_present)
        self.media_check = media_check
        self.wait = wait if wait is not None else time.sleep
        self.retries = retries
        if type(retries) is not int or not 1 <= retries <= 60:
            raise ValueError("Invalid wait limit")

    def _check(self, index):
        if not self.enabled or type(index) is not int or index != self.index:
            raise PermissionError("CLIENT systemd adapter not authorized")

    def _ctl(self, op, unit):
        if op not in ("start", "stop") or unit not in (
                (self.root_unit,) + self.bind_units):
            raise ValueError("Unit operation outside account")
        return self.run(["systemctl", op, unit]) is True

    def _active(self, unit):
        return self.run(["systemctl", "is-active", "--quiet", unit]) is True

    def _entries(self):
        return health.mount_entries(self.mountinfo())

    def _account_paths(self):
        root = plan.FUSE_ROOTS[self.index]
        binds = tuple((folder, destination) for _, i, folder, destination
                      in plan.BIND_MAP if i == self.index)
        return root, binds

    def stop(self, index):
        self._check(index)
        # No control operations for the other account, even if ours fails.
        for bind in reversed(self.bind_units):
            if not self._ctl("stop", bind):
                return False
        return self._ctl("stop", self.root_unit)

    def quiescent(self, index):
        self._check(index)
        try:
            root, binds = self._account_paths()
            mounts = self._entries()
            if any(path in mounts for path in
                   (root,) + tuple(dest for _, dest in binds)):
                return False
            if any(self._active(unit) for unit in
                   (self.root_unit,) + self.bind_units):
                return False
            return self.writer_present(plan.ACCOUNT_CONFS[index]) is False
        except (OSError, ValueError, TypeError, UnicodeError):
            return False

    def _root_ready(self):
        root, _ = self._account_paths()
        try:
            entry = self._entries().get(root)
            return (entry is not None and entry["fstype"] == "fuse.rclone"
                    and entry["fsroot"] == "/")
        except (OSError, ValueError, TypeError, UnicodeError):
            return False

    def start(self, index):
        self._check(index)
        if not self._ctl("start", self.root_unit):
            return False
        for attempt in range(self.retries):
            if self._root_ready():
                break
            if attempt + 1 < self.retries:
                self.wait(1)
        else:
            return False
        for bind in self.bind_units:
            if not self._ctl("start", bind):
                return False
        return True

    def healthy(self, index):
        self._check(index)
        if not callable(self.media_check):
            return False
        try:
            root, binds = self._account_paths()
            text = self.mountinfo()
            rows = text.splitlines()
            targets = (root,) + tuple(dest for _, dest in binds)
            # Detect overmounting of the selected account's paths.
            counts = {p: 0 for p in targets}
            for line in rows:
                columns = line.partition(" - ")[0].split()
                if len(columns) < 6:
                    return False
                point = health._decode(columns[4])
                if point in counts:
                    counts[point] += 1
            if any(count != 1 for count in counts.values()):
                return False
            entries = health.mount_entries(text)
            parent = entries.get(root)
            if (parent is None or parent["fstype"] != "fuse.rclone"
                    or parent["fsroot"] != "/"):
                return False
            for folder, path in binds:
                child = entries.get(path)
                if (child is None or child["fsroot"] != "/" + folder
                        or any(child[k] != parent[k]
                               for k in ("device", "source", "fstype"))):
                    return False
            if not all(self._active(u) for u in
                       (self.root_unit,) + self.bind_units):
                return False
            return self.media_check(index) is True
        except (OSError, ValueError, TypeError, UnicodeError):
            return False
