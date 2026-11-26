# -*- coding: utf-8 -*-
"""Intercambio transaccional de instalaciones Tvheadend.

No controla Kodi ni systemd.
No modifica addon_data ni bases de datos.
El llamador debe garantizar la parada del servicio.
"""

import ctypes
import fcntl
import hashlib
import json
import os
import re
import stat
import tempfile

from contextlib import contextmanager
from pathlib import Path

from lib.tvheadend_manifest import ADDON_ID
from lib.tvheadend_version import (
    read_installed_version,
    parse_version,
    compare_versions,
)


AT_FDCWD = -100
RENAME_EXCHANGE = 2

MAX_JOURNAL_BYTES = 16384

STATES = (
    "PREPARED",
    "SWAPPING",
    "SWAPPED",
    "ROLLING_BACK",
    "ROLLED_BACK",
)

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class TransactionError(RuntimeError):
    """Transaccion bloqueada o no confirmada."""


def require(condition, code):

    if not condition:
        raise TransactionError(code)


def sync_directory(path):

    fd = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY,
    )

    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def sync_tree(root):
    """Persiste archivos y directorios antes del swap."""

    for folder, dirs, files in os.walk(
        root,
        topdown=False,
        followlinks=False,
    ):

        directory = Path(folder)

        for name in dirs:

            path = directory / name

            require(
                stat.S_ISDIR(path.lstat().st_mode),
                "UNSAFE_TREE_DIRECTORY",
            )

        for name in files:

            path = directory / name

            require(
                stat.S_ISREG(path.lstat().st_mode),
                "UNSAFE_TREE_FILE",
            )

            fd = os.open(
                path,
                os.O_RDONLY | os.O_NOFOLLOW,
            )

            try:
                os.fsync(fd)
            finally:
                os.close(fd)

        sync_directory(directory)


def atomic_exchange(left, right):
    """Intercambio atomico Linux. Sin fallback."""

    libc = ctypes.CDLL(None, use_errno=True)

    exchange = getattr(libc, "renameat2", None)

    require(
        exchange is not None,
        "RENAMEAT2_UNAVAILABLE",
    )

    exchange.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]

    exchange.restype = ctypes.c_int

    result = exchange(
        AT_FDCWD,
        os.fsencode(left),
        AT_FDCWD,
        os.fsencode(right),
        RENAME_EXCHANGE,
    )

    if result != 0:

        error = ctypes.get_errno()

        raise OSError(
            error, os.strerror(error)
        )

    # Persiste ambas entradas de directorio.
    sync_directory(Path(left).parent)

    if Path(left).parent != Path(right).parent:
        sync_directory(Path(right).parent)


def identity(root):
    """Identifica version y binario principal."""

    root = Path(root)

    metadata = root / "addon.xml"
    binary = root / "bin" / "tvheadend"

    require(
        stat.S_ISREG(metadata.lstat().st_mode),
        "UNSAFE_ADDON_XML",
    )

    require(
        stat.S_ISDIR(
            binary.parent.lstat().st_mode
        ),
        "UNSAFE_BINARY_DIRECTORY",
    )

    mode = binary.lstat().st_mode

    require(
        stat.S_ISREG(mode) and mode & 0o111,
        "INVALID_EXECUTABLE",
    )

    version = read_installed_version(metadata)

    digest = hashlib.sha256()

    with binary.open("rb") as stream:

        for chunk in iter(
            lambda: stream.read(256 * 1024),
            b"",
        ):
            digest.update(chunk)

    return {
        "version": version,
        "binary_sha256": digest.hexdigest(),
    }


def validate_identity(data):

    require(
        isinstance(data, dict)
        and set(data) == {
            "version",
            "binary_sha256",
        },
        "INVALID_JOURNAL_IDENTITY",
    )

    try:
        parse_version(data["version"])
    except ValueError:
        raise TransactionError(
            "INVALID_JOURNAL_VERSION"
        ) from None

    digest = data["binary_sha256"]

    require(
        isinstance(digest, str)
        and SHA256_PATTERN.fullmatch(digest)
        is not None,
        "INVALID_JOURNAL_SHA256",
    )


class DirectoryTransaction:

    def __init__(self, active, root):

        self.active = Path(active)
        self.root = Path(root)

        self.candidate = self.root / "candidate"
        self.journal = self.root / "journal.json"
        self.lockfile = self.root / "transaction.lock"

    def _layout(self):

        require(
            self.active.name == ADDON_ID,
            "INVALID_ACTIVE_ADDON_PATH",
        )

        require(
            self.active.is_absolute()
            and self.root.is_absolute(),
            "ABSOLUTE_PATH_REQUIRED",
        )

        for path in (
            self.active,
            self.root,
            self.candidate,
        ):

            require(
                path.resolve() == path
                and stat.S_ISDIR(
                    path.lstat().st_mode
                ),
                "UNSAFE_TRANSACTION_DIRECTORY",
            )

        require(
            self.root != self.active.parent
            and self.active.parent
            not in self.root.parents
            and self.root not in self.active.parents,
            "STAGING_INSIDE_ADDON_TREE",
        )

        require(
            self.root.stat().st_uid == os.geteuid()
            and not (
                self.root.stat().st_mode & 0o077
            ),
            "TRANSACTION_DIRECTORY_NOT_PRIVATE",
        )

        require(
            self.active.stat().st_dev
            == self.candidate.stat().st_dev
            == self.root.stat().st_dev,
            "TRANSACTION_FILESYSTEM_MISMATCH",
        )

        require(
            not os.path.samefile(
                self.active,
                self.candidate,
            ),
            "IDENTICAL_TRANSACTION_DIRECTORIES",
        )

    @contextmanager
    def _locked(self):

        self._layout()

        fd = os.open(
            self.lockfile,
            os.O_RDWR
            | os.O_CREAT
            | os.O_NOFOLLOW,
            0o600,
        )

        try:

            require(
                stat.S_ISREG(
                    os.fstat(fd).st_mode
                ),
                "INVALID_TRANSACTION_LOCK",
            )

            try:
                fcntl.flock(
                    fd,
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB,
                )

            except BlockingIOError:
                raise TransactionError(
                    "TRANSACTION_BUSY"
                ) from None

            yield

        finally:
            os.close(fd)

    def _write(self, record):

        temp = None

        try:

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".journal-",
                dir=self.root,
                delete=False,
            ) as stream:

                temp = Path(stream.name)

                json.dump(
                    record,
                    stream,
                    sort_keys=True,
                )

                stream.write("\n")
                stream.flush()

                os.fsync(stream.fileno())

            os.replace(temp, self.journal)

            sync_directory(self.root)

        finally:

            if temp is not None and temp.exists():
                temp.unlink()

    def _read(self):

        require(
            self.journal.is_file()
            and not self.journal.is_symlink(),
            "JOURNAL_MISSING_OR_UNSAFE",
        )

        try:

            with self.journal.open("rb") as stream:
                raw = stream.read(
                    MAX_JOURNAL_BYTES + 1
                )

            require(
                0 < len(raw) <= MAX_JOURNAL_BYTES,
                "INVALID_JOURNAL_SIZE",
            )

            record = json.loads(raw)

        except (ValueError, OSError):
            raise TransactionError(
                "INVALID_JOURNAL"
            ) from None

        require(
            isinstance(record, dict)
            and set(record) == {
                "schema",
                "state",
                "old",
                "new",
            }
            and type(record["schema"]) is int
            and record["schema"] == 1
            and record["state"] in STATES,
            "INVALID_JOURNAL_SCHEMA",
        )

        validate_identity(record["old"])
        validate_identity(record["new"])

        require(
            compare_versions(
                record["new"]["version"],
                record["old"]["version"],
            ) > 0,
            "INVALID_JOURNAL_VERSION_ORDER",
        )

        return record

    def _orientation(self, record):

        active = identity(self.active)
        candidate = identity(self.candidate)

        if (
            active == record["old"]
            and candidate == record["new"]
        ):
            return "OLD_ACTIVE"

        if (
            active == record["new"]
            and candidate == record["old"]
        ):
            return "NEW_ACTIVE"

        raise TransactionError(
            "TRANSACTION_IDENTITY_MISMATCH"
        )

    def prepare(self):

        with self._locked():

            require(
                not os.path.lexists(self.journal),
                "JOURNAL_ALREADY_EXISTS",
            )

            old = identity(self.active)
            new = identity(self.candidate)

            require(
                compare_versions(
                    new["version"],
                    old["version"],
                ) > 0,
                "NOT_AN_UPGRADE",
            )

            sync_tree(self.active)
            sync_tree(self.candidate)

            sync_directory(self.active.parent)
            sync_directory(self.root)
            sync_directory(self.root.parent)

            record = {
                "schema": 1,
                "state": "PREPARED",
                "old": old,
                "new": new,
            }

            self._write(record)

            return record

    def inspect(self):

        with self._locked():

            record = self._read()

            return {
                "state": record["state"],
                "orientation": self._orientation(
                    record
                ),
            }

    def _switch(self, forward, assert_stopped):

        with self._locked():

            record = self._read()
            state = record["state"]

            orientation = self._orientation(record)

            if forward:

                require(
                    state in (
                        "PREPARED",
                        "SWAPPING",
                        "SWAPPED",
                    ),
                    "INVALID_FORWARD_STATE",
                )

                require(
                    state != "PREPARED"
                    or orientation == "OLD_ACTIVE",
                    "INVALID_PREPARED_ORIENTATION",
                )

                require(
                    state != "SWAPPED"
                    or orientation == "NEW_ACTIVE",
                    "INVALID_SWAPPED_ORIENTATION",
                )

                intent = "SWAPPING"
                completed = "SWAPPED"
                desired = "NEW_ACTIVE"

            else:

                require(
                    state != "ROLLED_BACK"
                    or orientation == "OLD_ACTIVE",
                    "INVALID_ROLLBACK_ORIENTATION",
                )

                intent = "ROLLING_BACK"
                completed = "ROLLED_BACK"
                desired = "OLD_ACTIVE"

            require(
                assert_stopped() is True,
                "SERVICE_STOP_NOT_CONFIRMED",
            )

            # Registrar intencion antes de tocar el disco.
            record["state"] = intent
            self._write(record)

            if orientation != desired:

                require(
                    assert_stopped() is True,
                    "SERVICE_STOP_NOT_CONFIRMED",
                )

                atomic_exchange(
                    self.active,
                    self.candidate,
                )

            require(
                self._orientation(record) == desired,
                "EXCHANGE_NOT_CONFIRMED",
            )

            # Persistir incluso al recuperar un intercambio
            # que termino antes de escribir el journal.
            sync_directory(self.active.parent)
            sync_directory(self.root)

            record["state"] = completed
            self._write(record)

            return completed

    def swap(self, assert_stopped):

        return self._switch(
            True, assert_stopped
        )

    def rollback(self, assert_stopped):

        return self._switch(
            False, assert_stopped
        )
