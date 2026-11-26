# -*- coding: utf-8 -*-
"""Reconciliacion y ciclo de vida del actualizador TVH."""

import fcntl
import os
import stat
import subprocess
import uuid

from contextlib import contextmanager
from pathlib import Path

from lib import tvheadend_boot as boot
from lib import tvheadend_boot_install as boot_install
from lib import tvheadend_backup as backup
from lib import tvheadend_health as health
from lib import tvheadend_transaction as tx
from lib import tvheadend_updater as updater


WRAPPER = "/usr/sbin/service-addon-wrapper"


class LifecycleError(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise LifecycleError(code)


def enable_native_service():

    require(
        boot_install.is_coreelec_root(),
        "WRAPPER_PLATFORM_REJECTED",
    )

    result = subprocess.run(
        [
            WRAPPER,
            "enable",
            tx.ADDON_ID,
            str(boot.ACTIVE_ADDON),
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )

    require(
        result.returncode == 0,
        "NATIVE_WRAPPER_FAILED",
    )


def inactive_service(state):

    return (
        state.load in ("loaded", "not-found")
        and state.active == "inactive"
        and state.sub == "dead"
        and state.pid == 0
        and state.control_pid == 0
        and state.unit_file in (
            "",
            "enabled",
            "disabled",
            "not-found",
        )
    )


def no_pending_job(ctl=boot_install.systemctl):

    jobs = ctl(
        "list-jobs",
        "--no-pager",
        "--no-legend",
    )

    return all(
        boot.TVH_UNIT not in line.split()
        for line in jobs.splitlines()
    )


def stop_for_update(
    *,
    ctl=boot_install.systemctl,
    read_state=health.read_service,
    scan_processes=health.find_tvheadend_processes,
):
    """Detener sin eliminar la unidad hasta validar su salida."""

    require(
        boot_install.verify_stop_timeout(ctl) is True,
        "STOP_TIMEOUT_NOT_CONFIRMED",
    )

    before = read_state()

    require(
        before.running,
        "STOP_INITIAL_SERVICE_NOT_RUNNING",
    )

    require(
        no_pending_job(ctl),
        "STOP_JOB_ALREADY_PENDING",
    )

    require(
        read_state() == before,
        "STOP_INITIAL_STATE_CHANGED",
    )

    # Una parada solicitada explicitamente no activa
    # Restart=always.

    ctl("stop", boot.TVH_UNIT)

    after = read_state()

    require(
        inactive_service(after)
        and after.load == "loaded"
        and after.unit_file == "enabled",
        "NATIVE_STOP_NOT_CONFIRMED",
    )

    result = boot_install.properties(
        ctl,
        boot.TVH_UNIT,
        "Result",
        "ExecMainCode",
        "ExecMainStatus",
    )

    require(
        result["Result"] == "success"
        and (
            result["ExecMainCode"],
            result["ExecMainStatus"],
        ) in (
            ("1", "0"),
            ("2", "15"),
        ),
        "NATIVE_STOP_UNCLEAN",
    )

    require(
        not scan_processes()
        and no_pending_job(ctl)
        and read_state() == after,
        "NATIVE_STOP_NOT_QUIESCENT",
    )

    return "STOPPED_CLEANLY"


def normalize_failed_stop(
    observed,
    enabled,
    *,
    ctl=boot_install.systemctl,
    read_state=health.read_service,
    scan_processes=health.find_tvheadend_processes,
):
    """Exclusivo de recuperacion bajo bloqueo de transaccion."""

    require(
        type(enabled) is bool
        and observed.failed_stop,
        "INVALID_FAILED_STOP_STATE",
    )

    if enabled:

        require(
            observed.load == "loaded"
            and observed.unit_file == "enabled",
            "FAILED_ENABLED_UNIT_MISMATCH",
        )

    else:

        require(
            observed.unit_file in (
                "", "disabled", "not-found"
            ),
            "FAILED_DISABLED_UNIT_MISMATCH",
        )

    require(
        not scan_processes()
        and no_pending_job(ctl)
        and read_state() == observed,
        "FAILED_STOP_NOT_QUIESCENT",
    )

    # No arranca procesos ni autoriza nuevas instalaciones.

    ctl("reset-failed", boot.TVH_UNIT)

    after = read_state()

    if enabled:

        require(
            inactive_service(after)
            and after.load == "loaded"
            and after.unit_file == "enabled",
            "FAILED_ENABLED_RESET_NOT_CONFIRMED",
        )

    else:

        require(
            after.stopped,
            "FAILED_DISABLED_RESET_NOT_CONFIRMED",
        )

    require(
        not scan_processes()
        and no_pending_job(ctl)
        and read_state() == after,
        "FAILED_STOP_RESET_NOT_QUIESCENT",
    )

    return after


def repair_enabled_service(
    kodi,
    identity,
    *,
    active=boot.ACTIVE_ADDON,
    read_state=health.read_service,
    scan_processes=health.find_tvheadend_processes,
    recovery_ready=boot_install.recovery_ready,
    enable_service=enable_native_service,
):
    """Repara exclusivamente un arranque ausente.

    No reinicia procesos activos ni modifica SQLite.
    La salud completa se verifica en el coordinador.
    """

    observed = kodi.state()

    require(
        observed.enabled
        and observed.version == identity["version"],
        "REPAIR_KODI_STATE_MISMATCH",
    )

    require(
        tx.identity(active) == identity,
        "REPAIR_DISK_IDENTITY_MISMATCH",
    )

    state = read_state()

    if state.running:
        return "ALREADY_RUNNING"

    if not inactive_service(state):
        return "NOT_REPAIRED"

    require(
        not scan_processes(),
        "REPAIR_RESIDUAL_PROCESS",
    )

    require(
        recovery_ready() is True,
        "REPAIR_BOOT_PROTECTION_NOT_READY",
    )

    require(
        kodi.state() == observed
        and read_state() == state
        and not scan_processes(),
        "REPAIR_STATE_CHANGED",
    )

    enable_service()

    # No devolver HEALTHY: aun falta verificar
    # proceso, hash, HTTP y HTSP.

    return "START_REQUESTED"


class Lifecycle:

    def __init__(self, root):

        self.root = Path(root)

        self.parent = self.root.parent

        self.history = (
            self.parent
            / (self.root.name + "-history")
        )

        self.lockfile = (
            self.parent
            / ("." + self.root.name + ".lock")
        )

        self._held = False

    @contextmanager
    def locked(self):

        backup.validate_directory(
            self.parent
        )

        require(
            self.root.resolve() == self.root,
            "UNSAFE_LIFECYCLE_ROOT",
        )

        info = self.parent.stat()

        require(
            info.st_uid == os.geteuid()
            and not info.st_mode & 0o022,
            "UNSAFE_LIFECYCLE_PARENT",
        )

        require(
            not self._held,
            "LIFECYCLE_ALREADY_LOCKED",
        )

        fd = os.open(
            self.lockfile,
            os.O_RDWR
            | os.O_CREAT
            | os.O_NOFOLLOW
            | os.O_NONBLOCK,
            0o600,
        )

        try:

            meta = os.fstat(fd)

            require(
                stat.S_ISREG(meta.st_mode)
                and meta.st_uid == os.geteuid()
                and meta.st_nlink == 1
                and not meta.st_mode & 0o077,
                "UNSAFE_LIFECYCLE_LOCK",
            )

            try:

                fcntl.flock(
                    fd,
                    fcntl.LOCK_EX
                    | fcntl.LOCK_NB,
                )

            except BlockingIOError:

                raise LifecycleError(
                    "LIFECYCLE_BUSY"
                ) from None

            self._held = True

            yield self

        finally:

            self._held = False

            os.close(fd)

    def archive_terminal(self, worker):
        """Archiva una transaccion terminal verificada.

        Requiere bloqueo estable externo al directorio
        que se va a mover.
        """

        require(
            self._held,
            "LIFECYCLE_LOCK_REQUIRED",
        )

        require(
            worker.root == self.root,
            "LIFECYCLE_WORKER_MISMATCH",
        )

        backup.validate_private(self.root)

        with worker._locked():

            record = worker._read()

            state = record["state"]

            require(
                state in updater.TERMINAL,
                "TRANSACTION_NOT_TERMINAL",
            )

            expected = (
                record["new"]
                if state == "COMMITTED"
                else record["old"]
            )

            require(
                tx.identity(worker.active) == expected,
                "ARCHIVE_ACTIVE_IDENTITY_MISMATCH",
            )

            # Confirmar salud antes de retirar
            # el journal de la ruta activa.

            worker._verify(expected)

            if not os.path.lexists(self.history):

                self.history.mkdir(mode=0o700)

                tx.sync_directory(
                    self.parent
                )

            backup.validate_private(
                self.history
            )

            require(
                self.root.stat().st_dev
                == self.history.stat().st_dev,
                "ARCHIVE_FILESYSTEM_MISMATCH",
            )

            name = (
                state.lower()
                + "-"
                + uuid.uuid4().hex
            )

            target = self.history / name

            require(
                not os.path.lexists(target),
                "ARCHIVE_ALREADY_EXISTS",
            )

            os.rename(
                self.root, target
            )

            tx.sync_directory(self.history)
            tx.sync_directory(self.parent)

            return target


    def archive_unstarted(self, worker):
        """Archiva preparaciones que nunca iniciaron instalacion."""

        require(
            self._held,
            "LIFECYCLE_LOCK_REQUIRED",
        )

        require(
            worker.root == self.root,
            "LIFECYCLE_WORKER_MISMATCH",
        )

        backup.validate_private(self.root)

        with worker._locked():

            require(
                not os.path.lexists(worker.journal)
                and not os.path.lexists(
                    worker.directory.journal
                ),
                "UNSTARTED_HAS_JOURNAL",
            )

            allowed = {
                "candidate",
                "update.lock",
                "transaction.lock",
                "release.json",
            }

            require(
                all(
                    path.name in allowed
                    for path in self.root.iterdir()
                ),
                "UNEXPECTED_UNSTARTED_CONTENT",
            )

            if not os.path.lexists(self.history):

                self.history.mkdir(mode=0o700)
                tx.sync_directory(self.parent)

            backup.validate_private(self.history)

            require(
                self.root.stat().st_dev
                == self.history.stat().st_dev,
                "ARCHIVE_FILESYSTEM_MISMATCH",
            )

            target = self.history / (
                "unstarted-" + uuid.uuid4().hex
            )

            require(
                not os.path.lexists(target),
                "ARCHIVE_ALREADY_EXISTS",
            )

            os.rename(self.root, target)

            tx.sync_directory(self.history)
            tx.sync_directory(self.parent)

            return target
