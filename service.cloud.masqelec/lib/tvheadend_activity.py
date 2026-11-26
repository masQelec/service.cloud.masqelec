# -*- coding: utf-8 -*-
"""Proteccion de actividad antes de actualizar Tvheadend.

Consultas de solo lectura mediante interfaces inyectadas.
Sin dependencias directas de Kodi, systemd o rclone.
"""

import json

from dataclasses import dataclass


DVR_GUARD_SECONDS = 900
BACKGROUND_GUARD_SECONDS = 120
API_TIMEOUT_SECONDS = 5

IDLE = "IDLE"

DEFERRED_KODI_PLAYBACK = "DEFERRED_KODI_PLAYBACK"
DEFERRED_TVH_SUBSCRIPTIONS = "DEFERRED_TVH_SUBSCRIPTIONS"
DEFERRED_RECORDING = "DEFERRED_RECORDING"
DEFERRED_UPCOMING_RECORDING = "DEFERRED_UPCOMING_RECORDING"
DEFERRED_BACKGROUND_ACTIVITY = "DEFERRED_BACKGROUND_ACTIVITY"
DEFERRED_ACTIVITY_UNKNOWN = "DEFERRED_ACTIVITY_UNKNOWN"

BACKGROUND_KEYS = (
    "ota_grabber",
    "int_grabber",
    "mux_scheduler",
)


@dataclass(frozen=True)
class ActivityDecision:
    status: str

    @property
    def allowed(self):
        return self.status == IDLE


def _unknown():
    return ActivityDecision(
        DEFERRED_ACTIVITY_UNKNOWN
    )


def _valid_number(value):
    return (
        type(value) is int
        and value >= 0
    )


def evaluate_tvh_activity(data):
    """Evalua una respuesta de status/activity."""

    if not isinstance(data, dict):
        return _unknown()

    now = data.get("current_time")
    subscriptions = data.get("subscription_count")
    connections = data.get("connection_count")
    activities = data.get("activities")

    if not (
        _valid_number(now)
        and now > 0
        and _valid_number(subscriptions)
        and _valid_number(connections)
        and isinstance(activities, dict)
    ):
        return _unknown()

    required = ("dvr",) + BACKGROUND_KEYS

    if not all(
        _valid_number(activities.get(key))
        for key in required
    ):
        return _unknown()

    dvr = activities["dvr"]

    if dvr != 0:

        remaining = dvr - now

        if remaining <= 0:
            return ActivityDecision(
                DEFERRED_RECORDING
            )

        if remaining <= DVR_GUARD_SECONDS:
            return ActivityDecision(
                DEFERRED_UPCOMING_RECORDING
            )

    if subscriptions > 0:
        return ActivityDecision(
            DEFERRED_TVH_SUBSCRIPTIONS
        )

    for key in BACKGROUND_KEYS:

        scheduled = activities[key]

        if (
            scheduled != 0
            and scheduled - now
            <= BACKGROUND_GUARD_SECONDS
        ):
            return ActivityDecision(
                DEFERRED_BACKGROUND_ACTIVITY
            )

    # Una conexion HTSP sin suscripcion activa
    # no implica reproduccion.
    return ActivityDecision(IDLE)


def check_kodi_activity(rpc_call):
    """Consulta Player.GetActivePlayers."""

    request = {
        "jsonrpc": "2.0",
        "method": "Player.GetActivePlayers",
        "id": 1,
    }

    try:

        response = json.loads(
            rpc_call(json.dumps(request))
        )

        if not (
            isinstance(response, dict)
            and response.get("jsonrpc") == "2.0"
            and type(response.get("id")) is int
            and response["id"] == 1
            and "error" not in response
            and isinstance(
                response.get("result"), list
            )
        ):
            return _unknown()

        if response["result"]:
            return ActivityDecision(
                DEFERRED_KODI_PLAYBACK
            )

        return ActivityDecision(IDLE)

    except Exception:
        return _unknown()


def check_activity(rpc_call, api_get):
    """Comprueba Kodi y Tvheadend sin modificar servicios.

    api_get utiliza el contrato existente de
    update_pvr._tvh_api_get_json:

        ok, code, data, body
    """

    kodi = check_kodi_activity(rpc_call)

    if not kodi.allowed:
        return kodi

    try:

        ok, code, data, _ = api_get(
            "status/activity",
            timeout_s=API_TIMEOUT_SECONDS,
        )

        if ok is not True or code != 200:
            return _unknown()

        tvh = evaluate_tvh_activity(data)

    except Exception:
        return _unknown()

    if not tvh.allowed:
        return tvh

    # Segunda observacion de Kodi: puede haber
    # comenzado una reproduccion durante la consulta TVH.
    return check_kodi_activity(rpc_call)
