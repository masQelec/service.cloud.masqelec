# -*- coding: utf-8 -*-
"""Recuperacion Tvheadend antes del arranque de Kodi.

Sin dependencias de xbmc, Internet ni rclone.
"""

import os
import subprocess

from pathlib import Path

from lib import tvheadend_health as health
from lib import tvheadend_updater as updater


ADDON_ROOT = Path(
    "/storage/.kodi/addons/"
    "service.cloud.masqelec"
)

TRANSACTION_ROOT = Path(
    "/storage/.kodi/userdata/addon_data/"
    "service.cloud.masqelec/tvheadend-update"
)

ACTIVE_ADDON = Path(
    "/storage/.kodi/addons/service.tvheadend43"
)

ACTIVE_CONFIG = Path(
    "/storage/.kodi/userdata/addon_data/"
    "service.tvheadend43"
)

UNIT_NAME = "masqelec-tvh-recovery.service"

DROPIN_NAME = "60-masqelec-tvh-recovery.conf"

STOP_DROPIN_NAME = "65-masqelec-tvh-stop.conf"

STOP_DROPIN = """[Service]
TimeoutStopSec=60s
"""

KODI_UNIT = "kodi.service"
TVH_UNIT = "service.tvheadend43.service"

UNIT = """[Unit]
Description=masQelec Tvheadend interrupted update recovery
DefaultDependencies=yes
RequiresMountsFor=/storage
After=local-fs.target
Before=kodi.service service.tvheadend43.service

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /storage/.kodi/addons/service.cloud.masqelec/tools/tvheadend_early_boot_run.py --recover
TimeoutStartSec=180
RemainAfterExit=yes
"""

KODI_DROPIN = """[Unit]
Wants=masqelec-tvh-recovery.service
After=masqelec-tvh-recovery.service
"""

TVH_DROPIN = """[Unit]
Requires=masqelec-tvh-recovery.service
After=masqelec-tvh-recovery.service
"""

PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "MainPID",
    "ControlPID",
)

SUCCESS_RESULTS = {
    "NO_PENDING",
    "FILES_RECOVERED",
    "COMMITTED",
    "ROLLED_BACK",
    "CANCELLED",
}


class BootRecoveryError(RuntimeError):
    """Recuperacion temprana no confirmada."""


def require(condition, code):

    if not condition:
        raise BootRecoveryError(code)


def parse_unit_state(raw):

    require(
        isinstance(raw, str)
        and len(raw) <= 8192,
        "INVALID_BOOT_UNIT_STATE",
    )

    values = {}

    for line in raw.splitlines():

        if not line:
            continue

        key, sep, value = line.partition("=")

        require(
            sep == "="
            and key in PROPERTIES
            and key not in values,
            "INVALID_BOOT_UNIT_PROPERTY",
        )

        values[key] = value

    require(
        set(values) == set(PROPERTIES),
        "INCOMPLETE_BOOT_UNIT_STATE",
    )

    return values


def read_unit_state(unit):

    require(
        unit in (KODI_UNIT, TVH_UNIT),
        "INVALID_BOOT_UNIT",
    )

    command = [
        "systemctl",
        "show",
        "--all",
        "--no-pager",
    ]

    command.extend(
        "-p" + prop
        for prop in PROPERTIES
    )

    command.append(unit)

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )

    values = parse_unit_state(
        result.stdout
    )

    require(
        result.returncode == 0
        or (
            result.returncode == 1
            and unit == TVH_UNIT
            and values["LoadState"] == "not-found"
        ),
        "BOOT_SYSTEMD_QUERY_FAILED",
    )

    return values


def unit_quiescent(unit, values):

    allowed_load = (
        ("loaded", "not-found")
        if unit == TVH_UNIT
        else ("loaded",)
    )

    return (
        values["LoadState"] in allowed_load
        and values["ActiveState"] == "inactive"
        and values["SubState"] == "dead"
        and values["MainPID"] == "0"
        and values["ControlPID"] == "0"
    )


def boot_quiescent(
    read_state=read_unit_state,
    scan_processes=health.find_tvheadend_processes,
):
    """Comprueba que ninguno de los servicios ha arrancado.

    El orden de systemd debe impedir su arranque
    concurrente durante toda la recuperacion.
    """

    try:

        before = {
            unit: read_state(unit)
            for unit in (KODI_UNIT, TVH_UNIT)
        }

        if not all(
            unit_quiescent(unit, values)
            for unit, values in before.items()
        ):
            return False

        if scan_processes():
            return False

        after = {
            unit: read_state(unit)
            for unit in (KODI_UNIT, TVH_UNIT)
        }

        return before == after

    except Exception:

        return False


def forbidden(*args, **kwargs):

    raise BootRecoveryError(
        "RUNTIME_OPERATION_DURING_EARLY_BOOT"
    )


def recover_pending(
    root=TRANSACTION_ROOT,
    active=ACTIVE_ADDON,
    config=ACTIVE_CONFIG,
    assert_quiescent=boot_quiescent,
):
    """Recupera exclusivamente archivos persistentes."""

    root = Path(root)

    require(
        root.is_absolute()
        and root.resolve() == root,
        "UNSAFE_BOOT_TRANSACTION_ROOT",
    )

    # Importacion local para evitar dependencia circular.
    from lib.tvheadend_lifecycle import Lifecycle

    if not os.path.lexists(root.parent):
        return "NO_PENDING"

    with Lifecycle(root).locked():

        return _recover_locked(
            root, active, config, assert_quiescent
        )


def _recover_locked(
    root, active, config, assert_quiescent
):

    if not os.path.lexists(root):
        return "NO_PENDING"

    worker = updater.TvheadendUpdater(
        active,
        config,
        root,
        kodi=None,
        is_stopped=forbidden,
        verify_health=forbidden,
        activity_allowed=forbidden,
        recovery_allowed=forbidden,
        notify=forbidden,
        wait=forbidden,
    )

    result = worker.recover_before_kodi(
        assert_quiescent
    )

    require(
        result in SUCCESS_RESULTS,
        "BOOT_RECOVERY_NOT_CONFIRMED",
    )

    return result
