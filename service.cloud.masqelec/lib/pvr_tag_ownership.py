"""G3-N: strict durable ownership registry for API-created TVH tags.

Never infer ownership from a tag name or old M3U. Missing registry starts
empty; invalid registry blocks all operations. Not called by production yet.
"""
import json
import os
from pathlib import Path
import re
import stat
import tempfile

_UUID = re.compile(r"^[0-9a-f]{32}$")


class RegistryBlocked(ValueError):
    pass


def _validate(values):
    if not isinstance(values, list):
        raise RegistryBlocked("INVALID_REGISTRY_ENTRIES")
    if any(not isinstance(x, str) or not _UUID.fullmatch(x) for x in values):
        raise RegistryBlocked("INVALID_OWNED_UUID")
    if len(set(values)) != len(values):
        raise RegistryBlocked("DUPLICATE_OWNED_UUID")
    return sorted(values)


def _private_dir(folder):
    folder = Path(folder)
    if folder.is_symlink():
        raise RegistryBlocked("REGISTRY_DIRECTORY_SYMLINK")
    if not folder.is_dir():
        raise RegistryBlocked("REGISTRY_DIRECTORY_MISSING")
    mode = folder.stat().st_mode
    if not stat.S_ISDIR(mode) or (mode & 0o077):
        raise RegistryBlocked("REGISTRY_DIRECTORY_NOT_PRIVATE")
    return folder


def load(path):
    path = Path(path)
    if path.is_symlink():
        raise RegistryBlocked("REGISTRY_SYMLINK")
    if not path.exists():
        _private_dir(path.parent)
        return []
    _private_dir(path.parent)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or (info.st_mode & 0o077):
        raise RegistryBlocked("REGISTRY_NOT_PRIVATE_FILE")
    if info.st_size > 64 * 1024:
        raise RegistryBlocked("REGISTRY_TOO_LARGE")
    try:
        with path.open("r", encoding="utf-8") as stream:
            raw = json.load(stream)
    except (OSError, ValueError, UnicodeError) as exc:
        raise RegistryBlocked("REGISTRY_UNREADABLE") from exc
    if not isinstance(raw, dict) or raw.get("version") != 1 or set(raw) != {"version", "uuids"}:
        raise RegistryBlocked("REGISTRY_SCHEMA_INVALID")
    return _validate(raw["uuids"])


def save(path, values):
    """Atomic replace + fsync. Caller must hold an exclusive cycle lock."""
    path = Path(path)
    values = _validate(list(values))
    folder = _private_dir(path.parent)
    if path.is_symlink():
        raise RegistryBlocked("REGISTRY_SYMLINK")
    if path.exists():
        load(path)  # refuse an invalid pre-existing registry
    payload = (json.dumps({"version": 1, "uuids": values},
                          separators=(",", ":"), sort_keys=True) + "\n").encode()
    fd = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".owned-tags-", dir=str(folder))
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            fd = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        tmp = None
        dirfd = os.open(str(folder), os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp is not None:
            os.unlink(tmp)
    if load(path) != values:
        raise RegistryBlocked("REGISTRY_VERIFY_FAILED")
    return values
