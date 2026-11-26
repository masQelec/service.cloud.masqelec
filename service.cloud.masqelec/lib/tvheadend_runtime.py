# -*- coding: utf-8 -*-
"""Adaptador comun MASTER/CLIENTE.

Todavia no conectado a los workers PVR.
Sin autorizacion explicita no realiza cambios.
"""

import os

from contextlib import contextmanager

from lib import tvheadend_activity as activity
from lib import tvheadend_boot as boot
from lib import tvheadend_boot_install as install
from lib import tvheadend_health as health
from lib import tvheadend_kodi as kodi
from lib import tvheadend_lifecycle as lifecycle
from lib import tvheadend_package as package
from lib import tvheadend_release_control as releases
from lib import tvheadend_updater as updater
from lib import tvheadend_update_service as service
from lib import tvheadend_version as version


NOTIFICATIONS = {
    "DOWNLOADING": (
        "Descargando actualizacion de Tvheadend",
        False,
    ),
    "INSTALLING": (
        "Actualizando Tvheadend",
        False,
    ),
    "UPDATED": (
        "Tvheadend actualizado correctamente",
        False,
    ),
    "ROLLED_BACK": (
        "Actualizacion fallida. Version anterior recuperada",
        True,
    ),
    "RECOVERY_REQUIRED": (
        "Tvheadend requiere recuperacion",
        True,
    ),
}


class RuntimeErrorTVH(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise RuntimeErrorTVH(code)


def protection_ready():

    try:
        return service.protection_ready() is True
    except Exception:
        return False


def prepare_boot_protection():

    if protection_ready():
        return "READY"

    require(
        install.is_coreelec_root(),
        "RUNTIME_PLATFORM_REJECTED",
    )

    root = boot.TRANSACTION_ROOT

    manager = lifecycle.Lifecycle(root)

    with manager.locked():

        for name in ("update.json", "journal.json"):

            require(
                not os.path.lexists(root / name),
                "BOOT_INSTALL_PENDING_TRANSACTION",
            )

        install.install_files(
            install.SYSTEMD_DIR,
            install.RUNNER,
        )

        install.systemctl("daemon-reload")

        require(
            install.verify_dependencies() is True,
            "BOOT_DEPENDENCIES_NOT_CONFIRMED",
        )

    # El ejecutor temprano adquiere el mismo bloqueo.
    # No mantenerlo durante systemctl start.

    if not install.recovery_ready():

        install.systemctl(
            "start",
            boot.UNIT_NAME,
        )

    require(
        protection_ready(),
        "BOOT_PROTECTION_NOT_READY",
    )

    return "READY"


def recovery_allowed(rpc_call, api_get):

    try:

        if not activity.check_kodi_activity(
            rpc_call
        ).allowed:

            return False

        observed = health.read_service()

        if observed.failed_stop:

            controller = kodi.KodiController(
                rpc_call,
                lambda *args: None,
            )

            addon_state = controller.state()

            observed = lifecycle.normalize_failed_stop(
                observed,
                addon_state.enabled,
            )

            if controller.state() != addon_state:
                return False

        if lifecycle.inactive_service(observed):

            return (
                not health.find_tvheadend_processes()
            )

        return activity.check_activity(
            rpc_call,
            api_get,
        ).allowed

    except Exception:

        return False


def make_notifier(xbmc, xbmcgui):

    def notify(event):

        if event not in NOTIFICATIONS:
            return

        message, failure = NOTIFICATIONS[event]

        try:

            xbmcgui.Dialog().notification(
                "Cloud masQelec",
                message,
                (
                    xbmcgui.NOTIFICATION_ERROR
                    if failure
                    else xbmcgui.NOTIFICATION_INFO
                ),
                5000,
                False,
            )

        except Exception:

            xbmc.log(
                "[masQelec] TVH notification failed",
                xbmc.LOGWARNING,
            )

    return notify


def run(
    *,
    branch,
    base,
    authorized=False,
    install_protection=False,
):

    if authorized is not True:
        return "NOT_AUTHORIZED"

    require(
        install.is_coreelec_root(),
        "RUNTIME_PLATFORM_REJECTED",
    )

    # Importaciones exclusivas del entorno Kodi.

    import xbmc
    import xbmcgui

    from lib.update_pvr import _tvh_api_get_json

    monitor = xbmc.Monitor()

    if monitor.abortRequested():
        return "DEFERRED_ABORT"

    if install_protection:

        prepare_boot_protection()

    controller = kodi.KodiController(
        xbmc.executeJSONRPC,
        xbmc.executebuiltin,
        wait=monitor.waitForAbort,
    )

    notify = make_notifier(
        xbmc, xbmcgui
    )

    def allowed():

        if monitor.abortRequested():
            return False

        return activity.check_activity(
            xbmc.executeJSONRPC,
            _tvh_api_get_json,
        ).allowed

    def verify_health(digest):

        return health.verify_running(
            digest,
            _tvh_api_get_json,
        )

    def repair(identity):

        return lifecycle.repair_enabled_service(
            controller,
            identity,
        )

    @contextmanager
    def stage(
        distribution,
        device,
        installed_version,
        branch,
        base,
        staging_parent,
    ):

        decision = version.decide_update(
            distribution,
            device,
            installed_version,
        )

        if decision.status == "UPDATE_AVAILABLE":

            notify("DOWNLOADING")

        with package.stage_update(
            distribution,
            device,
            installed_version,
            branch,
            base,
            staging_parent,
        ) as result:

            yield result

    worker = updater.TvheadendUpdater(
        boot.ACTIVE_ADDON,
        boot.ACTIVE_CONFIG,
        boot.TRANSACTION_ROOT,
        controller,
        health.is_stopped,
        verify_health,
        allowed,
        lambda: recovery_allowed(
            xbmc.executeJSONRPC,
            _tvh_api_get_json,
        ),
        notify=notify,
        wait=monitor.waitForAbort,
        repair_enabled=repair,
        stop_native=lifecycle.stop_for_update,
    )

    return service.run_cycle(
        worker,
        branch=branch,
        base=base,
        authorized=True,
        stage_package=stage,
        verify_protection=protection_ready,
        release_control=releases.ReleaseControl(
            boot.TRANSACTION_ROOT
        ),
    )
