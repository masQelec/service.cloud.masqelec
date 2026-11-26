# -*- coding: utf-8 -*-
"""Preparacion privada del paquete Tvheadend.

No modifica el addon activo, Kodi, systemd
ni la configuracion persistente.
"""

import hashlib
import os
import shutil
import stat
import zipfile

from pathlib import Path

from lib import tvheadend_package as package
from lib import tvheadend_manifest as manifest
from lib import tvheadend_transaction as transaction


MAX_GRABBER_BYTES = 128 * 1024
FREE_SPACE_RESERVE = 32 * 1024 * 1024


class StagingError(RuntimeError):
    """Preparacion rechazada."""


def require(condition, code):

    if not condition:
        raise StagingError(code)


def read_grabber(path):

    fd = os.open(
        path,
        os.O_RDONLY
        | os.O_NOFOLLOW
        | os.O_NONBLOCK,
    )

    try:

        require(
            stat.S_ISREG(os.fstat(fd).st_mode),
            "INVALID_GRABBER_FILE",
        )

        with os.fdopen(fd, "rb", closefd=False) as stream:

            raw = stream.read(
                MAX_GRABBER_BYTES + 1
            )

    finally:
        os.close(fd)

    require(
        0 < len(raw) <= MAX_GRABBER_BYTES,
        "INVALID_GRABBER_SIZE",
    )

    return raw


def validate_root(root):

    require(
        root.is_absolute()
        and root.resolve() == root
        and stat.S_ISDIR(root.lstat().st_mode),
        "INVALID_STAGING_ROOT",
    )

    info = root.stat()

    require(
        info.st_uid == os.geteuid()
        and not info.st_mode & 0o077,
        "STAGING_ROOT_NOT_PRIVATE",
    )

    require(
        not os.path.lexists(root / "journal.json"),
        "TRANSACTION_ALREADY_EXISTS",
    )

    require(
        not os.path.lexists(root / "candidate"),
        "CANDIDATE_ALREADY_EXISTS",
    )


def extract_validated_zip(zip_path, candidate):

    with zipfile.ZipFile(zip_path) as archive:

        for info in archive.infolist():

            parts = info.filename.rstrip("/").split("/")

            require(
                parts[0] == manifest.ADDON_ID
                and all(
                    part not in ("", ".", "..")
                    for part in parts
                )
                and "\\" not in info.filename,
                "UNSAFE_EXTRACTION_PATH",
            )

            destination = candidate.joinpath(
                *parts[1:]
            )

            if info.is_dir():

                destination.mkdir(
                    mode=0o755,
                    parents=True,
                    exist_ok=True,
                )

                continue

            destination.parent.mkdir(
                mode=0o755,
                parents=True,
                exist_ok=True,
            )

            total = 0

            with archive.open(info) as source:

                with destination.open("xb") as target:

                    while True:

                        chunk = source.read(
                            package.CHUNK_SIZE
                        )

                        if not chunk:
                            break

                        total += len(chunk)

                        require(
                            total <= info.file_size,
                            "EXTRACTION_SIZE_MISMATCH",
                        )

                        target.write(chunk)

            require(
                total == info.file_size,
                "EXTRACTION_SIZE_MISMATCH",
            )

            original_mode = info.external_attr >> 16

            # Conserva ejecutabilidad.
            # No importa permisos especiales ni
            # escritura de terceros desde el ZIP.

            mode = (
                0o755
                if original_mode & 0o111
                else 0o644
            )

            destination.chmod(mode)


def prepare_candidate(
    zip_path,
    entry,
    device,
    transaction_root,
    grabber_path,
):
    """Prepara candidate/ dentro del journal futuro.

    El ZIP debe proceder de staging privado.
    Esta funcion no concede autorizacion de instalar.
    """

    root = Path(transaction_root)

    validate_root(root)

    details = package.validate_zip(
        zip_path,
        entry,
        device,
    )

    grabber = read_grabber(grabber_path)

    needed = (
        details["unpacked_bytes"]
        + len(grabber)
        + FREE_SPACE_RESERVE
    )

    require(
        shutil.disk_usage(root).free >= needed,
        "INSUFFICIENT_STAGING_SPACE",
    )

    candidate = root / "candidate"

    # mkdir exclusivo: nunca sustituir un staging
    # o respaldo existente.

    candidate.mkdir(mode=0o755)

    try:

        extract_validated_zip(
            zip_path,
            candidate,
        )

        destination = (
            candidate / "bin" / "tv_grab_file"
        )

        if os.path.lexists(destination):

            require(
                stat.S_ISREG(
                    destination.lstat().st_mode
                ),
                "INVALID_PACKAGE_GRABBER",
            )

        with destination.open("wb") as stream:

            stream.write(grabber)
            stream.flush()
            os.fsync(stream.fileno())

        destination.chmod(0o755)

        observed = transaction.identity(candidate)

        require(
            observed["version"] == entry.version,
            "STAGED_VERSION_MISMATCH",
        )

        require(
            destination.read_bytes() == grabber,
            "GRABBER_PRESERVATION_FAILED",
        )

        transaction.sync_tree(candidate)
        transaction.sync_directory(root)

        return {
            "candidate": candidate,
            "version": observed["version"],
            "binary_sha256": observed["binary_sha256"],
            "grabber_sha256": (
                hashlib.sha256(grabber).hexdigest()
            ),
            "members": details["members"],
            "unpacked_bytes": details["unpacked_bytes"],
        }

    except BaseException:

        shutil.rmtree(candidate)
        raise
