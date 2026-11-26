# -*- coding: utf-8 -*-
"""Mantenimiento PVR comun MASTER/CLIENTE.

TVH administra canales, grupos, EPG y HTSP.
No se modifica TVxx.db ni se reconstruyen canales.
"""

import os

from lib import constants
from lib import log_utils
from lib import pvr_config
from lib import pvr_credentials
from lib import pvr_epg_settings
from lib import pvr_playlist

from lib import tvheadend_boot as boot
from lib import tvheadend_health as health
from lib import tvheadend_runtime as runtime
from lib import tvheadend_transaction as transaction

# Compatibilidad con el actualizador y los laboratorios.

from lib.pvr_http import (
    _tvh_api_get,
    _tvh_api_get_json,
    _tvh_api_post_form,
)


UPDATE_SUCCESS = {
    "UPDATED",
    "UP_TO_DATE",
    "NO_RELEASE",
    "LOCAL_NEWER",
}

RECOVERY_TERMINAL = {
    "NO_PENDING",
    "COMMITTED",
    "ROLLED_BACK",
    "CANCELLED",
}


def pending_transaction():

    return os.path.lexists(
        boot.TRANSACTION_ROOT
    )


def check_stack():

    identity = transaction.identity(
        boot.ACTIVE_ADDON
    )

    observed = health.verify_running(
        identity["binary_sha256"],
        _tvh_api_get_json,
    )

    if observed.get("health") != "PASS":
        raise RuntimeError(
            "TVHEADEND_HEALTH_NOT_CONFIRMED"
        )

    # Consulta de estado PVR, nunca toggle ni reinicio.

    import xbmcaddon

    addon = xbmcaddon.Addon("pvr.hts")

    if addon.getAddonInfo("id") != "pvr.hts":
        raise RuntimeError("PVR_ADDON_UNAVAILABLE")

    from lib import jsonrpc_utils

    ok, result, _ = jsonrpc_utils.jsonrpc_try(
        "Addons.GetAddonDetails",
        params={
            "addonid": "pvr.hts",
            "properties": ["enabled"],
        },
        retries=0,
        log_on_error=False,
    )

    if (
        not ok
        or not isinstance(result, dict)
        or result.get(
            "addon", {}
        ).get("enabled") is not True
    ):
        raise RuntimeError("PVR_ADDON_NOT_ENABLED")

    ok, result, _ = jsonrpc_utils.jsonrpc_try(
        "PVR.GetProperties",
        params={"properties": ["available"]},
        retries=0,
        log_on_error=False,
    )

    if (
        not ok
        or not isinstance(result, dict)
        or result.get("available") is not True
    ):
        raise RuntimeError("PVR_NOT_AVAILABLE")

    return "PASS"


def update_playlist():
    """Interfaz compatible, sin mantenimiento destructivo."""

    try:

        result = pvr_playlist.update(
            constants.CLOUD_RAW_BASE
        )

        log_utils.write_log(
            "[pvr][playlist] {} channels={}".format(
                result["status"],
                result["channels"],
            )
        )

        return True, result["status"] == "UPDATED"

    except Exception as error:

        log_utils.write_log(
            "[pvr][playlist] FAIL " + type(error).__name__,
            "WARNING",
        )

        return False, False


def update_pvr():

    steps = {}

    failures = []
    deferred = []

    branch = constants.CLOUD_BRANCH
    base = constants.CLOUD_RAW_BASE

    def finish():

        status = (
            "FAILED" if failures
            else "DEFERRED" if deferred
            else "OK"
        )

        log_utils.write_log(
            "[pvr] status={} steps={} failures={} deferred={}".format(
                status, steps, failures, deferred
            ),
            "WARNING" if status != "OK" else "INFO",
        )

        return {
            "status": status,
            "steps": steps,
            "failures": failures,
            "deferred": deferred,
        }

    def run_step(name, fn):

        try:

            result = fn()

            steps[name] = (
                result.get("status")
                if isinstance(result, dict)
                else result
            )

            return True, result

        except Exception as error:

            steps[name] = type(error).__name__
            failures.append(name)

            return False, None

    # 1. Recuperacion antes de ajustes o descargas.

    if pending_transaction():

        ok, outcome = run_step(
            "recovery",
            lambda: runtime.run(
                branch=branch,
                base=base,
                authorized=True,
                recover_only=True,
            ),
        )

        if (
            not ok
            or outcome not in RECOVERY_TERMINAL
            or pending_transaction()
        ):

            if "recovery" not in failures:
                failures.append("recovery")

            return finish()

        # No intentar instalar otro paquete
        # en el mismo ciclo de recuperacion.

        deferred.append("recovered_transaction")

        return finish()

    # 2. Credenciales antes de actualizar la playlist.

    credentials_ok, _ = run_step(
        "credentials",
        pvr_credentials.ensure_credentials,
    )

    if credentials_ok and steps["credentials"] not in (
        "PROVISIONED", "UNCHANGED",
    ):

        credentials_ok = False
        failures.append("credentials")

    # 3. La playlist siempre precede al actualizador TVH.

    playlist_ok = False

    if credentials_ok:

        playlist_ok, _ = run_step(
            "playlist",
            lambda: pvr_playlist.update(base),
        )

        if playlist_ok and steps["playlist"] not in (
            "UPDATED", "UNCHANGED",
        ):

            playlist_ok = False
            failures.append("playlist")

    # 4. Ajustes necesarios para el grabber nativo.

    settings_ok, settings = run_step(
        "xmltv_settings",
        lambda: pvr_epg_settings.ensure_settings(
            authorized=True
        ),
    )

    if settings_ok and settings not in (
        "UPDATED", "UNCHANGED"
    ):

        settings_ok = False
        failures.append("xmltv_settings")

    # No instalar un TVH nuevo si la playlist no esta lista.

    if playlist_ok and settings_ok:

        ok, outcome = run_step(
            "tvheadend_update",
            lambda: runtime.run(
                branch=branch,
                base=base,
                authorized=True,
                install_protection=True,
            ),
        )

        if ok:

            if outcome in UPDATE_SUCCESS:
                pass

            elif str(outcome).startswith("DEFERRED_"):
                deferred.append("tvheadend_update")

            else:
                failures.append("tvheadend_update")

    # No interferir con una transaccion pendiente.

    if pending_transaction():

        failures.append("pending_transaction")

        return finish()

    # 5. Configuracion mediante la API nativa.

    run_step(
        "tvheadend_config",
        lambda: pvr_config.ensure_config(
            authorized=True
        ),
    )

    # 6. Diagnostico final, sin resets.

    run_step(
        "health",
        check_stack,
    )

    return finish()
