# -*- coding: utf-8 -*-
"""Coordinador transaccional Tvheadend.

Recibe un paquete previamente preparado.
Las interfaces de Kodi y salud se inyectan.

No conectar al servicio de produccion hasta validar
la recuperacion temprana y los gates de integracion.
"""

import fcntl
import json
import os
import shutil
import tempfile
import time

from contextlib import contextmanager
from pathlib import Path

from lib import tvheadend_backup as backup
from lib import tvheadend_restore as restore
from lib import tvheadend_transaction as tx


STATES = {
    "PREPARED",
    "DISABLING",
    "BACKED_UP",
    "SWAPPED",
    "STARTING",
    "COMMITTED",
    "ROLLING_BACK",
    "ROLLBACK_STARTING",
    "ROLLED_BACK",
    "CANCELLED",
}

TERMINAL = {
    "COMMITTED",
    "ROLLED_BACK",
    "CANCELLED",
}

MAX_JOURNAL_BYTES = 16384


class UpdateError(RuntimeError):
    """Actualizacion no confirmada."""


def require(condition, code):
    if not condition:
        raise UpdateError(code)


def tree_hash(path):
    return backup.inventory(path)[1]["tree_sha256"]


class TvheadendUpdater:

    def __init__(
        self,
        active,
        config,
        root,
        kodi,
        is_stopped,
        verify_health,
        activity_allowed,
        recovery_allowed,
        notify=None,
        wait=None,
        repair_enabled=None,
        stop_native=None,
    ):

        self.active = Path(active)
        self.config = Path(config)
        self.root = Path(root)

        self.kodi = kodi
        self.is_stopped = is_stopped
        self.verify_health = verify_health

        self.activity_allowed = activity_allowed
        self.recovery_allowed = recovery_allowed

        self.notify = notify or (lambda event: None)
        self.wait = wait or time.sleep
        self.repair_enabled = repair_enabled
        self.stop_native = stop_native

        self.directory = tx.DirectoryTransaction(
            self.active, self.root
        )

        self.journal = self.root / "update.json"

    @contextmanager
    def _locked(self):

        backup.validate_private(self.root)

        fd = os.open(
            self.root / "update.lock",
            os.O_RDWR
            | os.O_CREAT
            | os.O_NOFOLLOW,
            0o600,
        )

        try:

            try:
                fcntl.flock(
                    fd,
                    fcntl.LOCK_EX | fcntl.LOCK_NB,
                )
            except BlockingIOError:
                raise UpdateError(
                    "UPDATE_BUSY"
                ) from None

            yield

        finally:
            os.close(fd)

    def _emit(self, event):

        # Un fallo de notificacion nunca debe
        # provocar la recuperacion del addon.

        try:
            self.notify(event)
        except Exception:
            pass

    def _write(self, record):

        temp = None

        try:

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.root,
                prefix=".update-",
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
            tx.sync_directory(self.root)

        finally:

            if temp is not None and temp.exists():
                temp.unlink()

    def _read(self):

        require(
            self.journal.is_file()
            and not self.journal.is_symlink(),
            "UPDATE_JOURNAL_MISSING",
        )

        with self.journal.open("rb") as stream:
            raw = stream.read(MAX_JOURNAL_BYTES + 1)

        require(
            0 < len(raw) <= MAX_JOURNAL_BYTES,
            "INVALID_UPDATE_JOURNAL_SIZE",
        )

        try:
            record = json.loads(raw)
        except ValueError:
            raise UpdateError(
                "INVALID_UPDATE_JOURNAL"
            ) from None

        require(
            isinstance(record, dict)
            and set(record) == {
                "schema",
                "state",
                "old",
                "new",
                "old_tree",
                "new_tree",
                "backup_sha",
                "restore_required",
            }
            and type(record["schema"]) is int
            and record["schema"] == 1
            and isinstance(record["state"], str)
            and record["state"] in STATES
            and type(record["restore_required"]) is bool,
            "INVALID_UPDATE_JOURNAL",
        )

        tx.validate_identity(record["old"])
        tx.validate_identity(record["new"])

        require(
            tx.compare_versions(
                record["new"]["version"],
                record["old"]["version"],
            ) > 0,
            "INVALID_UPDATE_VERSION_ORDER",
        )

        for key in (
            "old_tree",
            "new_tree",
            "backup_sha",
        ):

            value = record[key]

            require(
                value is None
                or (
                    isinstance(value, str)
                    and tx.SHA256_PATTERN.fullmatch(value)
                    is not None
                ),
                "INVALID_UPDATE_JOURNAL_HASH",
            )

        require(
            record["new_tree"] is not None,
            "MISSING_CANDIDATE_IDENTITY",
        )

        if record["restore_required"]:

            require(
                record["backup_sha"] is not None
                and record["old_tree"] is not None,
                "MISSING_RECOVERY_IDENTITY",
            )

        return record

    def _phase(self, record, state, **changes):

        updated = {
            **record,
            **changes,
            "state": state,
        }

        self._write(updated)

        return updated

    def _stop(self, record, *, for_update=False):

        observed = self.kodi.state()

        require(
            observed.version in (
                record["old"]["version"],
                record["new"]["version"],
            ),
            "UNEXPECTED_KODI_VERSION",
        )

        if for_update and self.stop_native is not None:

            require(
                observed.enabled,
                "NATIVE_STOP_ADDON_NOT_ENABLED",
            )

            require(
                self.stop_native() == "STOPPED_CLEANLY",
                "NATIVE_STOP_NOT_CONFIRMED",
            )

        if observed.enabled:

            self.kodi.set_enabled(
                False, observed.version
            )

        for attempt in range(20):

            if self.is_stopped() is True:
                return

            if attempt < 19:
                self.wait(1)

        raise UpdateError(
            "SERVICE_STOP_NOT_CONFIRMED"
        )

    def _verify(self, identity):

        for attempt in range(12):

            try:

                state = self.kodi.state()

                require(
                    state.enabled
                    and state.version == identity["version"],
                    "KODI_STATE_NOT_CONFIRMED",
                )

                require(
                    tx.identity(self.active) == identity,
                    "INSTALLED_IDENTITY_MISMATCH",
                )

                result = self.verify_health(
                    identity["binary_sha256"]
                )

                require(
                    isinstance(result, dict)
                    and result.get("health") == "PASS",
                    "HEALTH_NOT_CONFIRMED",
                )

                require(
                    self.kodi.state() == state,
                    "KODI_STATE_CHANGED",
                )

                return

            except Exception:

                if attempt < 11:
                    self.wait(1)

        raise UpdateError(
            "HEALTH_NOT_CONFIRMED"
        )

    def _enable(self, identity):

        expected = identity["version"]
        observed = self.kodi.state()

        if observed.enabled:

            require(
                observed.version == expected,
                "UNEXPECTED_ENABLED_VERSION",
            )

            if self.repair_enabled is not None:
                self.repair_enabled(identity)

        else:

            if observed.version != expected:

                self.kodi.rescan_disabled(
                    expected
                )

            self.kodi.set_enabled(
                True, expected
            )

        self._verify(identity)

    def _preflight(self):

        self.directory._layout()

        backup.validate_directory(self.config)

        require(
            self.config.name == backup.ADDON_ID,
            "INVALID_CONFIG_PATH",
        )

        require(
            self.config != self.active
            and self.config not in self.root.parents
            and self.root not in self.config.parents,
            "CONFIG_PATH_OVERLAP",
        )

        require(
            self.config.stat().st_dev
            == self.root.stat().st_dev,
            "CONFIG_FILESYSTEM_MISMATCH",
        )

        require(
            not os.path.lexists(self.journal)
            and not os.path.lexists(self.directory.journal)
            and not os.path.lexists(
                self.root / "config-backup"
            )
            and not os.path.lexists(
                self.root / "config-restore"
            ),
            "PENDING_TRANSACTION_EXISTS",
        )

        old = tx.identity(self.active)
        new = tx.identity(
            self.directory.candidate
        )

        require(
            tx.compare_versions(
                new["version"], old["version"]
            ) > 0,
            "NOT_AN_UPGRADE",
        )

        state = self.kodi.state()

        require(
            state.enabled
            and state.version == old["version"],
            "INITIAL_KODI_STATE_MISMATCH",
        )

        # Reservar espacio para respaldo y
        # una eventual copia de restauracion.

        summary = backup.inventory(
            self.config
        )[1]

        needed = (
            2 * (
                summary["bytes"]
                + summary["entries"] * 4096
            )
            + backup.FREE_SPACE_RESERVE
        )

        require(
            shutil.disk_usage(self.root).free >= needed,
            "INSUFFICIENT_RECOVERY_SPACE",
        )

        return {
            "schema": 1,
            "state": "PREPARED",
            "old": old,
            "new": new,
            "old_tree": None,
            "new_tree": tree_hash(
                self.directory.candidate
            ),
            "backup_sha": None,
            "restore_required": False,
        }

    def run(self):

        with self._locked():

            if self.activity_allowed() is not True:
                return "DEFERRED_ACTIVITY"

            record = self._preflight()

            self._write(record)

            try:

                # Repetir la comprobacion inmediatamente
                # antes de iniciar operaciones disruptivas.

                if self.activity_allowed() is not True:

                    self._phase(
                        record, "CANCELLED"
                    )

                    return "DEFERRED_ACTIVITY"

                record = self._phase(
                    record, "DISABLING"
                )

                self._emit("INSTALLING")

                self._stop(record, for_update=True)

                saved = backup.create_backup(
                    self.config,
                    self.root,
                    self.is_stopped,
                )

                require(
                    tree_hash(
                        self.directory.candidate
                    ) == record["new_tree"],
                    "STAGED_TREE_CHANGED",
                )

                require(
                    tx.identity(self.active)
                    == record["old"],
                    "OLD_INSTALLATION_CHANGED",
                )

                record = self._phase(
                    record,
                    "BACKED_UP",
                    backup_sha=saved["tree_sha256"],
                    old_tree=tree_hash(self.active),
                )

                self.directory.prepare()

                require(
                    tree_hash(
                        self.directory.candidate
                    ) == record["new_tree"],
                    "STAGED_TREE_CHANGED",
                )

                self.directory.swap(
                    self.is_stopped
                )

                require(
                    tree_hash(self.active)
                    == record["new_tree"],
                    "NEW_INSTALLATION_TREE_MISMATCH",
                )

                require(
                    tree_hash(
                        self.directory.candidate
                    ) == record["old_tree"],
                    "OLD_INSTALLATION_TREE_MISMATCH",
                )

                record = self._phase(
                    record, "SWAPPED"
                )

                self.kodi.rescan_disabled(
                    record["new"]["version"]
                )

                # Persistir antes de habilitar: la nueva
                # version podria modificar addon_data.

                record = self._phase(
                    record,
                    "STARTING",
                    restore_required=True,
                )

                self._enable(record["new"])

                self._phase(
                    record, "COMMITTED"
                )

            except Exception as original:

                try:

                    outcome = self._recover_locked()

                except Exception as recovery:

                    self._emit("RECOVERY_REQUIRED")

                    raise UpdateError(
                        "RECOVERY_REQUIRED"
                    ) from recovery

                if outcome == "ROLLED_BACK":
                    return outcome

                raise UpdateError(
                    "UPDATE_NOT_CONFIRMED"
                ) from original

            self._emit("UPDATED")

            return "UPDATED"

    def _rollback_files(self, record, assert_quiescent):

        require(
            assert_quiescent() is True,
            "RECOVERY_QUIESCENCE_NOT_CONFIRMED",
        )

        if os.path.lexists(
            self.directory.journal
        ):

            orientation = (
                self.directory.inspect()["orientation"]
            )

            if orientation == "NEW_ACTIVE":

                require(
                    tree_hash(
                        self.directory.candidate
                    ) == record["old_tree"],
                    "ROLLBACK_ADDON_INTEGRITY_FAILED",
                )

            self.directory.rollback(
                assert_quiescent
            )

        require(
            tx.identity(self.active)
            == record["old"],
            "ROLLBACK_BINARY_MISMATCH",
        )

        if record["old_tree"] is not None:

            require(
                tree_hash(self.active)
                == record["old_tree"],
                "ROLLBACK_TREE_MISMATCH",
            )

        if record["restore_required"]:

            restore.restore_configuration(
                self.config,
                self.root,
                record["backup_sha"],
                assert_quiescent,
            )


        require(
            assert_quiescent() is True,
            "RECOVERY_QUIESCENCE_NOT_CONFIRMED",
        )

    def recover_before_kodi(self, assert_quiescent):
        """Recuperacion offline sin API Kodi.

        El llamador debe impedir el arranque concurrente
        de Kodi y Tvheadend durante la recuperacion.
        """

        with self._locked():

            if not os.path.lexists(self.journal):

                require(
                    not os.path.lexists(
                        self.directory.journal
                    ),
                    "ORPHAN_DIRECTORY_JOURNAL",
                )

                return "NO_PENDING"

            record = self._read()

            if record["state"] in TERMINAL:
                return record["state"]

            require(
                assert_quiescent() is True,
                "BOOT_QUIESCENCE_NOT_CONFIRMED",
            )

            if record["state"] == "PREPARED":

                require(
                    not os.path.lexists(
                        self.directory.journal
                    ),
                    "UNEXPECTED_DIRECTORY_JOURNAL",
                )

                require(
                    tx.identity(self.active)
                    == record["old"],
                    "PREPARED_IDENTITY_MISMATCH",
                )

                self._phase(
                    record, "CANCELLED"
                )

                return "CANCELLED"

            if record["state"] == "ROLLBACK_STARTING":

                require(
                    tx.identity(self.active)
                    == record["old"],
                    "ROLLBACK_BINARY_MISMATCH",
                )

                return "FILES_RECOVERED"

            record = self._phase(
                record, "ROLLING_BACK"
            )

            self._rollback_files(
                record, assert_quiescent
            )

            require(
                assert_quiescent() is True,
                "BOOT_QUIESCENCE_NOT_CONFIRMED",
            )

            self._phase(
                record, "ROLLBACK_STARTING"
            )

            return "FILES_RECOVERED"

    def _recover_locked(self):

        record = self._read()

        if record["state"] in TERMINAL:
            return record["state"]

        if record["state"] == "PREPARED":

            self._phase(record, "CANCELLED")

            return "CANCELLED"

        require(
            self.recovery_allowed() is True,
            "RECOVERY_NOT_AUTHORIZED",
        )

        if record["state"] != "ROLLBACK_STARTING":

            record = self._phase(
                record, "ROLLING_BACK"
            )

            self._stop(record)

            self._rollback_files(
                record, self.is_stopped
            )

            self.kodi.rescan_disabled(
                record["old"]["version"]
            )

            # Desde este punto no restaurar otra vez
            # la configuracion: la version anterior
            # podria haber arrancado.

            record = self._phase(
                record,
                "ROLLBACK_STARTING",
            )

        self._enable(record["old"])

        self._phase(
            record, "ROLLED_BACK"
        )

        self._emit("ROLLED_BACK")

        return "ROLLED_BACK"

    def recover(self):

        with self._locked():

            return self._recover_locked()
