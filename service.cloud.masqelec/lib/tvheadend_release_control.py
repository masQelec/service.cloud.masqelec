# -*- coding: utf-8 -*-
"""Control persistente de paquetes fallidos y retencion."""

import hashlib
import json
import os
import re
import shutil
import stat

from pathlib import Path

from lib import tvheadend_backup as backup
from lib import tvheadend_transaction as tx
from lib import rclone_two_mount_atomic_install as atomic


METADATA = "release.json"

TARGETS = {
    "Amlogic-ng.arm",
    "Amlogic-ne.aarch64",
}

ARCHIVE_PATTERN = re.compile(
    r"(committed|rolled_back|cancelled|unstarted)-[0-9a-f]{32}"
)


class ReleaseControlError(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise ReleaseControlError(code)


def encode(data):

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def read_private(path):

    info = path.lstat()

    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and info.st_nlink == 1
        and not info.st_mode & 0o077
        and 0 < info.st_size <= 16384,
        "UNSAFE_RELEASE_METADATA",
    )

    fd = os.open(
        path,
        os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
    )

    try:
        return os.read(fd, 16385)
    finally:
        os.close(fd)


def validate_release(data):

    require(
        isinstance(data, dict)
        and set(data) == {
            "target", "version", "sha256"
        },
        "INVALID_RELEASE_IDENTITY",
    )

    require(
        data["target"] in TARGETS,
        "INVALID_RELEASE_TARGET",
    )

    require(
        isinstance(data["version"], str)
        and re.fullmatch(
            r"[0-9]{1,4}\.[0-9]{1,4}\.[0-9]{1,4}",
            data["version"],
        ) is not None,
        "INVALID_RELEASE_VERSION",
    )

    require(
        isinstance(data["sha256"], str)
        and re.fullmatch(
            r"[0-9a-f]{64}", data["sha256"]
        ) is not None,
        "INVALID_RELEASE_SHA256",
    )

    return data


def release_identity(entry):

    return validate_release({
        "target": entry.target,
        "version": entry.version,
        "sha256": entry.sha256,
    })


class ReleaseControl:

    def __init__(self, root):

        self.root = Path(root)

        self.failed = (
            self.root.parent
            / (self.root.name + "-failed")
        )

        self.history = (
            self.root.parent
            / (self.root.name + "-history")
        )

    def failure_path(self, release):

        key = hashlib.sha256(
            encode(validate_release(release))
        ).hexdigest()

        return self.failed / (key + ".json")

    def blocked(self, entry):

        release = release_identity(entry)

        if not os.path.lexists(self.failed):
            return False

        backup.validate_private(self.failed)

        path = self.failure_path(release)

        if not os.path.lexists(path):
            return False

        require(
            read_private(path) == encode(release),
            "FAILED_RELEASE_METADATA_MISMATCH",
        )

        return True

    def record_candidate(self, entry, candidate):

        backup.validate_private(self.root)

        release = release_identity(entry)

        observed = tx.identity(candidate)

        require(
            observed["version"] == release["version"],
            "RELEASE_CANDIDATE_VERSION_MISMATCH",
        )

        record = {
            "release": release,
            "binary_sha256": observed["binary_sha256"],
        }

        atomic.install_exclusive(
            str(self.root / METADATA),
            encode(record),
            0o600,
        )

    def before_archive(self, record):

        # Solo se penalizan rollbacks.
        # Cancelaciones y aplazamientos no cuentan.

        if record["state"] != "ROLLED_BACK":
            return

        # restore_required se persiste antes de habilitar
        # el candidato. Si nunca se alcanzo esa fase,
        # el fallo no demuestra un paquete defectuoso.

        if record.get("restore_required") is not True:
            return

        raw = read_private(
            self.root / METADATA
        )

        data = json.loads(raw)

        require(
            isinstance(data, dict)
            and set(data) == {
                "release", "binary_sha256"
            },
            "INVALID_RELEASE_RECORD",
        )

        release = validate_release(
            data["release"]
        )

        require(
            record["new"]["version"]
            == release["version"]
            and record["new"]["binary_sha256"]
            == data["binary_sha256"],
            "FAILED_RELEASE_JOURNAL_MISMATCH",
        )

        if not os.path.lexists(self.failed):

            self.failed.mkdir(mode=0o700)
            tx.sync_directory(self.failed.parent)

        backup.validate_private(self.failed)

        target = self.failure_path(release)

        expected = encode(release)

        if os.path.lexists(target):

            require(
                read_private(target) == expected,
                "FAILED_RELEASE_METADATA_MISMATCH",
            )

        else:

            atomic.install_exclusive(
                str(target),
                expected,
                0o600,
            )

    def prune_history(self):
        """Conserva el archivo mas reciente de cada clase.

        No elimina la transaccion activa ni archivos
        desconocidos. Ejecutar bajo Lifecycle.locked().
        """

        if not os.path.lexists(self.history):
            return 0

        backup.validate_private(self.history)

        groups = {}
        removed = 0

        for path in self.history.iterdir():

            match = ARCHIVE_PATTERN.fullmatch(
                path.name
            )

            if not match:
                continue

            if path.is_symlink():
                continue

            try:

                backup.validate_private(path)

                kind = match.group(1)

                update = path / "update.json"
                journal = path / "journal.json"

                if kind == "unstarted":

                    if (
                        os.path.lexists(update)
                        or os.path.lexists(journal)
                    ):
                        continue

                else:

                    record = json.loads(
                        read_private(update)
                    )

                    if (
                        record.get("schema") != 1
                        or record.get("state")
                        != kind.upper()
                    ):
                        continue

                groups.setdefault(
                    kind, []
                ).append(path)

            except (
                OSError,
                ValueError,
                RuntimeError,
                TypeError,
                AttributeError,
            ):
                # Conservar archivos dudosos.
                continue

        for paths in groups.values():

            paths.sort(
                key=lambda path: (
                    path.stat().st_ctime_ns,
                    path.name,
                ),
                reverse=True,
            )

            for obsolete in paths[1:]:

                backup.validate_private(obsolete)

                shutil.rmtree(obsolete)

                tx.sync_directory(self.history)

                removed += 1

        return removed
