# -*- coding: utf-8 -*-
"""Respaldo consistente de addon_data de Tvheadend.

Requiere servicio detenido y bloqueo exclusivo externo.
No modifica la configuracion original ni controla Kodi.
"""

import hashlib
import json
import os
import shutil
import stat
import tempfile

from pathlib import Path

from lib.tvheadend_manifest import ADDON_ID
from lib.tvheadend_transaction import (
    sync_directory,
    sync_tree,
)


MAX_BACKUP_BYTES = 256 * 1024 * 1024
MAX_BACKUP_ENTRIES = 20000
FREE_SPACE_RESERVE = 32 * 1024 * 1024

CHUNK_SIZE = 256 * 1024


class BackupError(RuntimeError):
    """Respaldo rechazado o no confirmado."""


def require(condition, code):

    if not condition:
        raise BackupError(code)


def require_stopped(assert_stopped):

    require(
        assert_stopped() is True,
        "SERVICE_STOP_NOT_CONFIRMED",
    )


def validate_directory(path):

    require(
        path.is_absolute()
        and path.resolve() == path
        and stat.S_ISDIR(path.lstat().st_mode),
        "UNSAFE_BACKUP_DIRECTORY",
    )


def validate_private(path):

    validate_directory(path)

    info = path.stat()

    require(
        info.st_uid == os.geteuid()
        and not info.st_mode & 0o077,
        "BACKUP_ROOT_NOT_PRIVATE",
    )


def read_file(path, expected_size, target=None):
    """Lectura acotada de archivo regular sin seguir enlaces."""

    fd = os.open(
        path,
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_NONBLOCK,
    )

    digest = hashlib.sha256()
    total = 0

    with os.fdopen(fd, "rb") as source:

        before = os.fstat(source.fileno())

        require(
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1,
            "UNSAFE_BACKUP_FILE",
        )

        require(
            before.st_size == expected_size,
            "BACKUP_FILE_CHANGED",
        )

        while True:

            raw = source.read(
                min(
                    CHUNK_SIZE,
                    expected_size - total + 1,
                )
            )

            if not raw:
                break

            total += len(raw)

            require(
                total <= expected_size,
                "BACKUP_FILE_CHANGED",
            )

            digest.update(raw)

            if target is not None:
                target.write(raw)

        after = os.fstat(source.fileno())

        require(
            total == expected_size
            and before.st_size == after.st_size
            and before.st_mtime_ns == after.st_mtime_ns
            and before.st_ctime_ns == after.st_ctime_ns,
            "BACKUP_FILE_CHANGED",
        )

    return digest.hexdigest()


def inventory(root):
    """Inventario completo, incluyendo directorios vacios."""

    root = Path(root)

    validate_directory(root)

    device = root.stat().st_dev

    records = {}
    total = 0
    files = 0

    def walk_error(exc):
        raise exc

    for folder, dirs, names in os.walk(
        root,
        followlinks=False,
        onerror=walk_error,
    ):

        directory = Path(folder)

        paths = [directory]

        for name in dirs:
            child = directory / name
            info = child.lstat()

            require(
                stat.S_ISDIR(info.st_mode)
                and info.st_dev == device,
                "UNSAFE_BACKUP_DIRECTORY",
            )

        paths.extend(
            directory / name
            for name in names
        )

        for path in paths:

            info = path.lstat()

            require(
                info.st_dev == device,
                "BACKUP_FILESYSTEM_MISMATCH",
            )

            rel = str(path.relative_to(root))

            record = {
                "mode": stat.S_IMODE(info.st_mode),
                "uid": info.st_uid,
                "gid": info.st_gid,
            }

            if stat.S_ISDIR(info.st_mode):

                record["kind"] = "directory"

            elif stat.S_ISREG(info.st_mode):

                require(
                    info.st_nlink == 1,
                    "BACKUP_HARDLINK_REJECTED",
                )

                total += info.st_size
                files += 1

                require(
                    total <= MAX_BACKUP_BYTES,
                    "BACKUP_SIZE_LIMIT",
                )

                record.update({
                    "kind": "file",
                    "size": info.st_size,
                    "sha256": read_file(
                        path, info.st_size
                    ),
                })

            else:

                raise BackupError(
                    "UNSAFE_BACKUP_FILE"
                )

            records[rel] = record

            require(
                len(records) <= MAX_BACKUP_ENTRIES,
                "BACKUP_ENTRY_LIMIT",
            )

    encoded = json.dumps(
        records,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    summary = {
        "schema": 1,
        "files": files,
        "entries": len(records),
        "bytes": total,
        "tree_sha256": hashlib.sha256(
            encoded
        ).hexdigest(),
    }

    return records, summary


def preserve_metadata(source, destination):

    info = source.lstat()
    current = destination.lstat()

    if (
        current.st_uid != info.st_uid
        or current.st_gid != info.st_gid
    ):

        os.chown(
            destination,
            info.st_uid,
            info.st_gid,
            follow_symlinks=False,
        )

    shutil.copystat(
        source,
        destination,
        follow_symlinks=False,
    )


def copy_file(source, destination, record):

    with destination.open("xb") as target:

        digest = read_file(
            source,
            record["size"],
            target,
        )

        target.flush()
        os.fsync(target.fileno())

    require(
        digest == record["sha256"],
        "BACKUP_SOURCE_CHANGED",
    )

    preserve_metadata(
        source, destination
    )


def copy_inventory(source, destination, records):

    directories = sorted(
        (
            name for name, entry in records.items()
            if entry["kind"] == "directory"
        ),
        key=lambda name: (
            len(Path(name).parts), name
        ),
    )

    for name in directories:

        path = destination / name

        path.mkdir(
            mode=0o700,
            exist_ok=False,
        )

    for name, record in records.items():

        if record["kind"] != "file":
            continue

        copy_file(
            source / name,
            destination / name,
            record,
        )

    # Aplicar metadatos de directorios al final.

    for name in reversed(directories):

        preserve_metadata(
            source / name,
            destination / name,
        )


def verify_backup(backup_path):

    backup = Path(backup_path)

    validate_private(backup)

    metadata = backup / "metadata.json"

    require(
        stat.S_ISREG(
            metadata.lstat().st_mode
        ),
        "UNSAFE_BACKUP_METADATA",
    )

    try:

        with metadata.open("rb") as stream:

            raw = stream.read(4097)

        require(
            0 < len(raw) <= 4096,
            "INVALID_BACKUP_METADATA",
        )

        expected = json.loads(raw)

    except (OSError, ValueError):

        raise BackupError(
            "INVALID_BACKUP_METADATA"
        ) from None

    _, observed = inventory(
        backup / "data"
    )

    require(
        expected == observed,
        "BACKUP_INTEGRITY_MISMATCH",
    )

    return observed


def create_backup(
    source_path,
    transaction_root,
    assert_stopped,
):
    """Crea y publica un respaldo verificado.

    El llamador mantiene un bloqueo exclusivo
    durante toda la operacion.
    """

    source = Path(source_path)
    root = Path(transaction_root)

    validate_directory(source)
    validate_private(root)

    require(
        source.name == ADDON_ID,
        "INVALID_BACKUP_SOURCE",
    )

    require(
        source != root
        and source not in root.parents
        and root not in source.parents,
        "BACKUP_PATH_OVERLAP",
    )

    final = root / "config-backup"

    require(
        not os.path.lexists(final),
        "BACKUP_ALREADY_EXISTS",
    )

    require_stopped(assert_stopped)

    records, summary = inventory(source)

    # Reserva adicional para bloques de disco,
    # directorios y archivos pequenos.

    needed = (
        summary["bytes"]
        + summary["entries"] * 4096
        + FREE_SPACE_RESERVE
    )

    require(
        shutil.disk_usage(root).free >= needed,
        "INSUFFICIENT_BACKUP_SPACE",
    )

    temp = Path(
        tempfile.mkdtemp(
            prefix=".config-backup-",
            dir=root,
        )
    )

    try:

        require_stopped(assert_stopped)

        destination = temp / "data"

        copy_inventory(
            source, destination, records
        )

        copied_records, copied = inventory(
            destination
        )

        require(
            copied_records == records
            and copied == summary,
            "BACKUP_INTEGRITY_MISMATCH",
        )

        require_stopped(assert_stopped)

        current_records, current = inventory(
            source
        )

        require(
            current_records == records
            and current == summary,
            "BACKUP_SOURCE_CHANGED",
        )

        metadata = temp / "metadata.json"

        with metadata.open(
            "x", encoding="utf-8"
        ) as stream:

            json.dump(
                summary,
                stream,
                sort_keys=True,
            )

            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())

        metadata.chmod(0o600)

        sync_tree(temp)

        require_stopped(assert_stopped)

        require(
            not os.path.lexists(final),
            "BACKUP_ALREADY_EXISTS",
        )

        os.rename(temp, final)

        sync_directory(root)

        result = verify_backup(final)

        return {
            "path": final,
            **result,
        }

    finally:

        if temp.exists():
            shutil.rmtree(temp)
