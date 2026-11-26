# -*- coding: utf-8 -*-
"""Punto de entrada aislado del actualizador Tvheadend.

Todavia no conectado al mantenimiento PVR.
No instala el protector systemd por su cuenta.
"""

import os

from pathlib import Path

from lib import tvheadend_backup as backup
from lib import tvheadend_boot_install as boot_install
from lib import tvheadend_boot_policy as boot_policy
from lib import tvheadend_lifecycle as lifecycle
from lib import tvheadend_package as package
from lib import tvheadend_platform as platform
from lib import tvheadend_staging as staging
from lib import tvheadend_transaction as tx
from lib import tvheadend_updater as updater
from lib import tvheadend_version as version


class UpdateServiceError(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise UpdateServiceError(code)


def protection_ready():

    return (
        boot_install.verify_dependencies() is True
        and boot_install.recovery_ready() is True
        and boot_install.verify_stop_timeout() is True
    )


def run_cycle(
    worker,
    *,
    branch,
    base,
    authorized=False,
    detect_device=platform.detect,
    fetch_manifest=package.fetch_manifest,
    stage_package=package.stage_update,
    prepare_candidate=staging.prepare_candidate,
    verify_protection=protection_ready,
    verify_recovery=boot_install.recovery_ready,
    verify_policy=boot_policy.policy_ready,
    release_control=None,
    recover_only=False,
    verify_playlist=None,
):
    """Ejecuta una iteracion completa bajo bloqueo persistente.

    La recuperacion local tiene prioridad sobre la descarga.
    La instalacion requiere autorizacion explicita.
    """

    if authorized is not True:
        return "NOT_AUTHORIZED"

    root = Path(worker.root)

    manager = lifecycle.Lifecycle(root)

    with manager.locked():

        # Resolver transacciones anteriores antes
        # de detectar plataforma o acceder a Internet.

        if os.path.lexists(root):

            backup.validate_private(root)

            has_update = os.path.lexists(
                worker.journal
            )

            has_directory = os.path.lexists(
                worker.directory.journal
            )

            require(
                has_update or not has_directory,
                "ORPHAN_DIRECTORY_JOURNAL",
            )

            if has_update:

                record = worker._read()

                if record["state"] in updater.TERMINAL:

                    outcome = record["state"]

                else:

                    require(
                        verify_recovery() is True,
                        "RECOVERY_UNIT_NOT_READY",
                    )

                    outcome = worker.recover()

                require(
                    outcome in updater.TERMINAL,
                    "RECOVERY_NOT_TERMINAL",
                )

                if release_control is not None:
                    release_control.before_archive(
                        worker._read()
                    )

                manager.archive_terminal(worker)

                if release_control is not None:
                    release_control.prune_history()

                # No reinstalar inmediatamente
                # tras recuperar una version fallida.

                return outcome

            manager.archive_unstarted(worker)

        if recover_only:
            return "NO_PENDING"

        if verify_policy() is not True:
            return "DEFERRED_UPDATE_POLICY"

        installed = tx.identity(worker.active)

        state = worker.kodi.state()

        require(
            state.enabled
            and state.version == installed["version"],
            "INITIAL_KODI_STATE_MISMATCH",
        )

        device = detect_device()

        try:

            distribution = fetch_manifest(
                branch, base
            )

        except package.ManifestNotPublished:

            return "NO_RELEASE"

        # Consultar versiones no interrumpe Kodi ni Tvheadend.
        selected = version.decide_update(
            distribution, device,
            installed["version"],
        )

        if release_control is not None:
            release_control.prune_history()

        if selected.status in (
            "UP_TO_DATE",
            "LOCAL_NEWER",
        ):
            return selected.status

        require(
            selected.status == "UPDATE_AVAILABLE",
            "INVALID_UPDATE_DECISION",
        )

        if release_control is not None:
            if release_control.blocked(selected.package):
                return "FAILED_PACKAGE_BLOCKED"

        # La descarga e instalacion siguen protegidas.
        if worker.activity_allowed() is not True:
            return "DEFERRED_ACTIVITY"

        if verify_playlist is not None:

            observed = verify_playlist()

            if observed != "CONVERGED":

                return (
                    observed
                    if observed in (
                        "DEFERRED_PLAYLIST_CONVERGENCE",
                        "DEFERRED_PLAYLIST_CONVERGENCE_UNKNOWN",
                    )
                    else "DEFERRED_PLAYLIST_CONVERGENCE_UNKNOWN"
                )

        with stage_package(
            distribution,
            device,
            installed["version"],
            branch,
            base,
            root.parent,
        ) as (decision, zip_path):

            if decision.status in (
                "UP_TO_DATE",
                "LOCAL_NEWER",
            ):

                require(
                    zip_path is None,
                    "UNEXPECTED_STAGED_PACKAGE",
                )

                return decision.status

            require(
                decision.status == "UPDATE_AVAILABLE"
                and zip_path is not None
                and decision.package is not None,
                "INVALID_UPDATE_DECISION",
            )

            require(
                verify_protection() is True,
                "BOOT_PROTECTION_NOT_READY",
            )

            if worker.activity_allowed() is not True:
                return "DEFERRED_ACTIVITY"

            if verify_playlist is not None:

                observed = verify_playlist()

                if observed != "CONVERGED":

                    return (
                        observed
                        if observed in (
                            "DEFERRED_PLAYLIST_CONVERGENCE",
                            "DEFERRED_PLAYLIST_CONVERGENCE_UNKNOWN",
                        )
                        else "DEFERRED_PLAYLIST_CONVERGENCE_UNKNOWN"
                    )

            require(
                tx.identity(worker.active) == installed,
                "INSTALLED_VERSION_CHANGED",
            )

            require(
                worker.kodi.state() == state,
                "KODI_STATE_CHANGED",
            )

            if verify_policy() is not True:
                return "DEFERRED_UPDATE_POLICY"

            root.mkdir(mode=0o700)

            tx.sync_directory(root.parent)

            prepare_candidate(
                zip_path,
                decision.package,
                device,
                root,
            )

            require(
                tx.identity(worker.active) == installed,
                "INSTALLED_VERSION_CHANGED",
            )

            require(
                verify_protection() is True,
                "BOOT_PROTECTION_NOT_READY",
            )

            if verify_policy() is not True:
                manager.archive_unstarted(worker)
                return "DEFERRED_UPDATE_POLICY"

            if release_control is not None:
                release_control.record_candidate(
                    decision.package,
                    root / "candidate",
                )

            outcome = worker.run()

        # El contexto de descarga ya ha terminado.
        # Ahora podemos mover la transaccion completa.

        if os.path.lexists(worker.journal):

            record = worker._read()

            require(
                record["state"] in updater.TERMINAL,
                "UPDATE_NOT_TERMINAL",
            )

            if release_control is not None:
                release_control.before_archive(record)

            manager.archive_terminal(worker)

        else:

            require(
                outcome == "DEFERRED_ACTIVITY",
                "UPDATE_JOURNAL_MISSING",
            )

            manager.archive_unstarted(worker)

        if release_control is not None:
            release_control.prune_history()

        return outcome
