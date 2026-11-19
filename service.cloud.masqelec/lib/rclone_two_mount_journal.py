# -*- coding: utf-8 -*-
"""Journal privado y durable para un FUTURO cutover, sin ejecutar montajes.

El directorio persistente contiene secretos. Nunca se publica ni registra.
El estado se guarda mediante rename + fsync. La existencia de una transacción
con phase != prepared exige recuperación explícita antes de reactivar legacy.
No hay adaptador operativo conectado en esta etapa.
"""
import fcntl
import json
import os
import shutil
import stat
import tempfile
from contextlib import contextmanager

from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout

SCHEMA = 1
PHASES = (
    "prepared", "cutover_started", "active",
    "rollback_required", "legacy_restored",
)
NEXT = {
    "prepared": {"cutover_started"},
    "cutover_started": {"active", "rollback_required"},
    "active": {"rollback_required"},
    "rollback_required": {"legacy_restored"},
    "legacy_restored": set(),
}
FILES = ("canonical.conf",) + rollout.LEGACY_SERVICES


def _private_dir(path):
    info = os.lstat(path)
    if (not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o700
            or info.st_uid != os.geteuid()):
        raise ValueError("Unsafe journal directory")


def _write_new(path, content):
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(content)
            f.flush()
        os.fsync(fd)
    finally:
        os.close(fd)


def _replace_private(path, content):
    folder = os.path.dirname(path)
    fd, temp = tempfile.mkstemp(prefix=".phase-", dir=folder)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(content)
            f.flush()
        os.fsync(fd)
        os.replace(temp, path)
        _sync(folder)
    finally:
        os.close(fd)
        if os.path.exists(temp):
            os.unlink(temp)


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _state_bytes(phase):
    if phase not in PHASES:
        raise ValueError("Invalid journal phase")
    return (json.dumps({
        "schema": SCHEMA, "layout": rollout.LAYOUT,
        "candidate_id": rollout.CANDIDATE_ID, "phase": phase,
    }, sort_keys=True) + "\n").encode("utf-8")


def _trusted_base(base):
    """Allow CoreELEC's root-owned shared state root, not secret directories."""
    if base == "/storage/.config/masqelec" and os.geteuid() == 0:
        info = os.lstat(base)
        if (not stat.S_ISDIR(info.st_mode)
                or info.st_uid != 0
                or stat.S_IMODE(info.st_mode) not in (0o700, 0o755)):
            raise ValueError("Unsafe journal base directory")
    else:
        _private_dir(base)


@contextmanager
def locked(parent):
    """Bloqueo exclusivo por dispositivo, sin seguir .lock symlink."""
    # First install on CoreELEC: /storage/.config/masqelec may be absent.
    # Create exactly one private intermediate directory, never following a
    # symlink or silently trusting an existing group-writable ancestor.
    base = os.path.dirname(parent)
    if not os.path.lexists(base):
        ancestor = os.path.dirname(base)
        info = os.lstat(ancestor)
        if (not stat.S_ISDIR(info.st_mode)
                or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) & 0o022):
            raise ValueError("Unsafe journal ancestor")
        os.mkdir(base, 0o700)
        _sync(ancestor)
    # /storage/.config/masqelec is shared with other addon state and may
    # already exist as root-owned 0755 on CoreELEC. Never chmod it: only
    # the dedicated transaction directory may contain private credentials.
    _trusted_base(base)
    os.makedirs(parent, mode=0o700, exist_ok=True)
    _private_dir(parent)
    lock = os.path.join(parent, ".lock")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock, flags, 0o600)
    try:
        info = os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o600
                or info.st_uid != os.geteuid()):
            raise ValueError("Unsafe journal lock")
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def prepare(parent, raw_conf, legacy_units):
    """Almacena respaldo privado PREVIO al corte; no cambia system.d.

    Debe invocarse con bloqueo locked(parent) y antes de parar legacy.
    La transacción no se sobreescribe si ya existía.
    """
    _private_dir(parent)
    if set(legacy_units) != set(rollout.LEGACY_SERVICES):
        raise ValueError("Unexpected legacy unit inventory")
    plan.generate(raw_conf, legacy_units)  # OAuth/crypt e identidad validados.
    target = os.path.join(parent, rollout.CANDIDATE_ID)
    if os.path.lexists(target):
        raise ValueError("Existing journal requires manual inspection")
    temp = tempfile.mkdtemp(prefix=".cutover-", dir=parent)
    try:
        _private_dir(temp)
        _write_new(os.path.join(temp, "canonical.conf"), raw_conf)
        for name in rollout.LEGACY_SERVICES:
            _write_new(os.path.join(temp, name), legacy_units[name])
        _write_new(os.path.join(temp, "phase.json"), _state_bytes("prepared"))
        _sync(temp)
        if os.path.lexists(target):
            raise ValueError("Concurrent transaction")
        os.rename(temp, target)
        temp = None
        _sync(parent)
        return target
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)


def phase(target):
    """Solo estado, sin valores secretos; evita enlaces y JSON ambiguo."""
    _private_dir(target)
    file = os.path.join(target, "phase.json")
    info = os.lstat(file)
    if (not stat.S_ISREG(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_uid != os.geteuid()
            or info.st_size > 4096):
        raise ValueError("Invalid journal state")
    fd = os.open(file, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        raw = os.read(fd, 4097)
    finally:
        os.close(fd)
    obj = json.loads(raw)
    if (not isinstance(obj, dict) or set(obj) != {
            "schema", "layout", "candidate_id", "phase"}
            or type(obj["schema"]) is not int
            or obj["schema"] != SCHEMA
            or obj["layout"] != rollout.LAYOUT
            or obj["candidate_id"] != rollout.CANDIDATE_ID
            or obj["phase"] not in PHASES):
        raise ValueError("Unsupported journal phase")
    return obj["phase"]


def transition(target, expected, new_phase):
    """Únicamente transición monotónica, bajo locked(parent)."""
    current = phase(target)
    if current != expected or new_phase not in NEXT[current]:
        raise ValueError("Unsafe journal transition")
    _replace_private(os.path.join(target, "phase.json"),
                     _state_bytes(new_phase))
    return new_phase


def needs_manual_recovery(parent):
    """Lectura conservadora: ausencia=seguro; incierto=NO seguro."""
    target = os.path.join(parent, rollout.CANDIDATE_ID)
    if not os.path.lexists(target):
        return False
    try:
        return phase(target) not in ("prepared", "legacy_restored")
    except (OSError, ValueError, TypeError, UnicodeError):
        return True
