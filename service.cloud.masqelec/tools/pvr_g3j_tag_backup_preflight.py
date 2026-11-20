#!/usr/bin/env python3
"""G3-J: private local backup and conservative reference preflight.

No TVH/Kodi mutations. Do not share the created backup: it may contain
configuration metadata. Never assume that restoring a file while TVH is
running is safe or that idnode/create preserves UUID.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

UUID = "3e6be21d508c4effb8de6195294739b9"
NAME = "ES - NBA"
TAGDIR = Path("/storage/.kodi/userdata/addon_data/service.tvheadend43/channel/tag")
TVH_CONFIG = TAGDIR.parent.parent
BACKUP_ROOT = Path("/storage/.cache/masqelec-g3-backup")
MAX_FILE = 1024 * 1024
MAX_SCAN_FILES = 25000
MAX_SCAN_BYTES = 128 * 1024 * 1024

def _regular_bytes(path, max_size=MAX_FILE):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > max_size:
        raise ValueError("INVALID_OR_OVERSIZE_TAG")
    with path.open("rb") as handle:
        content = handle.read(max_size + 1)
    if len(content) > max_size:
        raise ValueError("TAG_TOO_LARGE")
    return content

def _backup_tag():
    raw = _regular_bytes(TAGDIR / UUID)
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError("INVALID_TAG_JSON") from exc
    if not isinstance(obj, dict) or obj.get("name") != NAME or obj.get("internal") is not False:
        raise ValueError("TAG_IDENTITY_MISMATCH")
    # Exclusive directory creation protects against reusing old backups.
    if BACKUP_ROOT.is_symlink():
        raise ValueError("BACKUP_ROOT_SYMLINK")
    BACKUP_ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    if BACKUP_ROOT.is_symlink():
        raise ValueError("BACKUP_ROOT_SYMLINK")
    os.chmod(BACKUP_ROOT, 0o700)
    dest = BACKUP_ROOT / ("tag-" + UUID + "-" + str(time.time_ns()) + ".json")
    fd = os.open(str(dest), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if _regular_bytes(dest) != raw:
            raise ValueError("BACKUP_VERIFY_FAILED")
        return dest, hashlib.sha256(raw).hexdigest()
    except BaseException:
        try:
            dest.unlink()
        except OSError:
            pass
        raise

def _scan_references():
    """Best-effort bounded reference scan; cannot prove absence globally."""
    hits = []
    examined = 0
    unreadable = 0
    skipped = 0
    seen_bytes = 0
    token = UUID.encode("ascii")
    for root, dirs, files in os.walk(str(TVH_CONFIG), followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
        for filename in files:
            path = Path(root) / filename
            if path == TAGDIR / UUID:
                continue
            examined += 1
            if examined > MAX_SCAN_FILES:
                raise ValueError("REFERENCE_SCAN_LIMIT_FILES")
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    skipped += 1
                    continue
                seen_bytes += info.st_size
                if seen_bytes > MAX_SCAN_BYTES:
                    raise ValueError("REFERENCE_SCAN_LIMIT_BYTES")
                with path.open("rb") as stream:
                    if token in stream.read(MAX_FILE + 1):
                        hits.append(path)
                    if info.st_size > MAX_FILE:
                        skipped += 1
            except ValueError:
                raise
            except OSError:
                unreadable += 1
    return len(hits), examined, unreadable, skipped

def main():
    if not TAGDIR.is_dir() or TAGDIR.is_symlink():
        raise ValueError("TAG_DIRECTORY_UNAVAILABLE")
    backup, digest = _backup_tag()
    print("=== G3-J PRIVATE BACKUP / NO TVH WRITES ===")
    print("TARGET_TAG=" + NAME)
    print("BACKUP_CREATED=YES")
    print("BACKUP_PATH=" + str(backup))
    print("BACKUP_SHA256=" + digest)
    print("BACKUP_VERIFIED=YES")
    hits, examined, unreadable, skipped = _scan_references()
    print("CONFIG_REFERENCES_FOUND=" + str(hits))
    print("CONFIG_FILES_EXAMINED=" + str(examined))
    print("CONFIG_FILES_UNREADABLE=" + str(unreadable))
    print("CONFIG_FILES_SKIPPED_OR_TRUNCATED=" + str(skipped))
    print("REFERENCE_SCAN_EXHAUSTIVE=NO")
    print("UUID_RESTORE_PROVEN=NO")
    print("OWNERSHIP_VERIFIED=NO")
    print("DELETE_AUTHORIZED=NO")
    return 0 if not hits and not unreadable and not skipped else 2

if __name__ == "__main__":
    try:
        sys.exit(main())
    except (Exception, KeyboardInterrupt) as exc:
        print("G3J=BLOCKED")
        print("ERROR_TYPE=" + type(exc).__name__)
        print("DELETE_AUTHORIZED=NO")
        sys.exit(2)
