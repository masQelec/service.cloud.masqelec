# -*- coding: utf-8 -*-
"""Proteccion de actividad antes de actualizar Tvheadend.

Consultas de solo lectura mediante interfaces inyectadas.
Sin dependencias directas de Kodi, systemd o rclone.
"""

import json
import time

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



LEGACY_GRID_LIMIT = 10000
LEGACY_EPG_AFTER_SECONDS = 900


def _legacy_data(api_get, endpoint, grid=False):

    options = {
        "timeout_s": API_TIMEOUT_SECONDS,
    }

    if grid:

        options["query"] = {
            "start": 0,
            "limit": LEGACY_GRID_LIMIT,
        }

    ok, code, data, _ = api_get(
        endpoint, **options
    )

    if (
        ok is not True
        or code != 200
        or not isinstance(data, dict)
    ):
        raise ValueError("LEGACY_API_UNAVAILABLE")

    return data


def _legacy_entries(api_get, endpoint, grid=False):

    data = _legacy_data(api_get, endpoint, grid)

    entries = data.get("entries")

    total = data.get(
        "total", data.get("totalCount")
    )

    if (
        not isinstance(entries, list)
        or type(total) is not int
        or not 0 <= total <= LEGACY_GRID_LIMIT
        or total != len(entries)
        or not all(
            isinstance(row, dict)
            for row in entries
        )
    ):
        raise ValueError("LEGACY_GRID_INCOMPLETE")

    return entries


def _cron_field(value, maximum):

    result = set()

    for item in value.split(","):

        if item == "*":

            result.update(range(maximum + 1))

        elif item.startswith("*/"):

            step = item[2:]

            if not step.isascii() or not step.isdigit():
                raise ValueError("INVALID_CRON_STEP")

            step = int(step)

            if not 1 <= step <= maximum + 1:
                raise ValueError("INVALID_CRON_STEP")

            result.update(
                range(0, maximum + 1, step)
            )

        elif item.isascii() and item.isdigit():

            number = int(item)

            if not 0 <= number <= maximum:
                raise ValueError("INVALID_CRON_VALUE")

            result.add(number)

        else:

            raise ValueError("UNSUPPORTED_CRON")

    return result


def _daily_schedule(value):

    if not isinstance(value, str) or len(value) > 4096:
        raise ValueError("INVALID_CRON")

    result = set()

    for line in value.splitlines():

        line = line.strip()

        if not line or line.startswith("#"):
            continue

        fields = line.split()

        # Soporte explicito para horarios diarios.
        # No interpretar expresiones desconocidas.

        if len(fields) != 5 or fields[2:] != ["*"] * 3:
            raise ValueError("UNSUPPORTED_CRON")

        minutes = _cron_field(fields[0], 59)

        hours = _cron_field(fields[1], 23)

        result.update(
            (hour, minute)
            for hour in hours
            for minute in minutes
        )

    return result


def _epg_schedule(api_get):

    data = _legacy_data(
        api_get, "epggrab/config/load"
    )

    entries = data.get("entries")

    if (
        not isinstance(entries, list)
        or len(entries) != 1
        or not isinstance(entries[0], dict)
    ):
        raise ValueError("INVALID_EPG_CONFIG")

    params = entries[0].get("params")

    if not isinstance(params, list):
        raise ValueError("INVALID_EPG_CONFIG")

    properties = {}

    for prop in params:

        if not isinstance(prop, dict):
            raise ValueError("INVALID_EPG_PROPERTY")

        name = prop.get("id")

        if (
            not isinstance(name, str)
            or name in properties
        ):
            raise ValueError("INVALID_EPG_PROPERTY")

        properties[name] = prop.get("value")

    internal = _daily_schedule(
        properties.get("cron")
    )

    ota = _daily_schedule(
        properties.get("ota_cron")
    )

    timeout = properties.get("ota_timeout")

    if (
        type(timeout) is not int
        or not 0 <= timeout <= 86400
    ):
        raise ValueError("INVALID_OTA_TIMEOUT")

    return internal, ota, timeout


def _schedule_near(now, schedule, after):

    if not schedule:
        return False

    first = ((now - after) // 60) * 60

    last = (
        (now + BACKGROUND_GUARD_SECONDS) // 60
    ) * 60

    for instant in range(first, last + 1, 60):

        # Proteccion conservadora ante diferencias
        # entre la configuracion horaria del servicio
        # y la del proceso Kodi.

        for clock in (time.localtime, time.gmtime):

            observed = clock(instant)

            if (
                observed.tm_hour,
                observed.tm_min,
            ) in schedule:

                if (
                    -after
                    <= instant - now
                    <= BACKGROUND_GUARD_SECONDS
                ):
                    return True

    return False


def check_legacy_activity(api_get, now=None):

    """Proteccion legacy de solo lectura.

    Los horarios EPG no certifican el estado interno
    del grabber. La parada ordenada sigue siendo
    obligatoria.
    """

    try:

        if _legacy_entries(
            api_get, "status/subscriptions"
        ):
            return ActivityDecision(
                DEFERRED_TVH_SUBSCRIPTIONS
            )

        if _legacy_entries(
            api_get, "status/inputs"
        ):
            return ActivityDecision(
                DEFERRED_BACKGROUND_ACTIVITY
            )

        recordings = _legacy_entries(
            api_get,
            "dvr/entry/grid_upcoming",
            grid=True,
        )

        current = (
            int(time.time()) if now is None else now
        )

        if not _valid_number(current) or current <= 0:
            return _unknown()

        for row in recordings:

            enabled = row.get("enabled")
            status = row.get("sched_status")

            if type(enabled) is not bool:
                return _unknown()

            if not isinstance(status, str):
                return _unknown()

            if status.lower().startswith("recording"):
                return ActivityDecision(
                    DEFERRED_RECORDING
                )

            if not enabled:
                continue

            start = row.get("start_real")
            stop = row.get("stop_real")

            if (
                status != "scheduled"
                or not _valid_number(start)
                or not _valid_number(stop)
                or not 0 < start < stop
            ):
                return _unknown()

            remaining = start - current

            if remaining <= 0:
                return ActivityDecision(
                    DEFERRED_RECORDING
                )

            if remaining <= DVR_GUARD_SECONDS:
                return ActivityDecision(
                    DEFERRED_UPCOMING_RECORDING
                )

        # Los clientes IPTV observados no tienen
        # programaciones de mux. Una configuracion
        # diferente requiere soporte explicito.

        if _legacy_entries(
            api_get,
            "mpegts/mux_sched/grid",
            grid=True,
        ):
            return _unknown()

        internal, ota, timeout = _epg_schedule(
            api_get
        )

        if now is None:
            current = int(time.time())

        if (
            _schedule_near(
                current,
                internal,
                LEGACY_EPG_AFTER_SECONDS,
            )
            or _schedule_near(
                current,
                ota,
                max(
                    timeout,
                    LEGACY_EPG_AFTER_SECONDS,
                ),
            )
        ):
            return ActivityDecision(
                DEFERRED_BACKGROUND_ACTIVITY
            )

        # Repetir las comprobaciones activas al
        # terminar las consultas de programacion.

        if _legacy_entries(
            api_get, "status/subscriptions"
        ):
            return ActivityDecision(
                DEFERRED_TVH_SUBSCRIPTIONS
            )

        if _legacy_entries(
            api_get, "status/inputs"
        ):
            return ActivityDecision(
                DEFERRED_BACKGROUND_ACTIVITY
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

        if ok is False and code == 404:

            tvh = check_legacy_activity(api_get)

        elif ok is True and code == 200:

            tvh = evaluate_tvh_activity(data)

        else:

            return _unknown()

    except Exception:
        return _unknown()

    if not tvh.allowed:
        return tvh

    # Segunda observacion de Kodi: puede haber
    # comenzado una reproduccion durante la consulta TVH.
    return check_kodi_activity(rpc_call)
