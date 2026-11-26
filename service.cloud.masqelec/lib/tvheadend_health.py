# -*- coding: utf-8 -*-
"""Verificacion de salud de Tvheadend.

Solo lectura: no controla servicios ni modifica Kodi.
"""

import hashlib
import os
import re
import socket
import subprocess

from dataclasses import dataclass
from pathlib import Path


UNIT = "service.tvheadend43.service"

BINARY = Path(
    "/storage/.kodi/addons/"
    "service.tvheadend43/bin/tvheadend"
)

PROPERTIES = (
    "LoadState",
    "ActiveState",
    "SubState",
    "MainPID",
    "ControlPID",
    "UnitFileState",
)

HTTP_TIMEOUT = 5
HTSP_TIMEOUT = 3
HTSP_PORT = 9982

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class HealthError(RuntimeError):
    """Estado del servicio no confirmado."""


def require(condition, code):

    if not condition:
        raise HealthError(code)


@dataclass(frozen=True)
class ServiceState:

    load: str
    active: str
    sub: str
    pid: int
    control_pid: int
    unit_file: str

    @property
    def running(self):

        return (
            self.load == "loaded"
            and self.active == "active"
            and self.sub == "running"
            and self.pid > 0
            and self.control_pid == 0
            and self.unit_file == "enabled"
        )

    @property
    def stopped(self):

        return (
            self.load in (
                "loaded", "not-found"
            )
            and self.active == "inactive"
            and self.sub == "dead"
            and self.pid == 0
            and self.control_pid == 0
            and self.unit_file in (
                "", "disabled", "not-found"
            )
        )


    @property
    def failed_stop(self):

        return (
            self.load in ("loaded", "not-found")
            and self.active == "failed"
            and self.sub == "failed"
            and self.pid == 0
            and self.control_pid == 0
            and self.unit_file in (
                "", "enabled", "disabled", "not-found"
            )
        )


def parse_service(raw):

    require(
        isinstance(raw, str)
        and len(raw) <= 8192,
        "INVALID_SYSTEMD_OUTPUT",
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
            "INVALID_SYSTEMD_PROPERTY",
        )

        values[key] = value

    require(
        set(values) == set(PROPERTIES),
        "INCOMPLETE_SYSTEMD_STATE",
    )

    for key in ("MainPID", "ControlPID"):

        require(
            re.fullmatch(
                r"[0-9]{1,10}",
                values[key],
            ) is not None,
            "INVALID_SYSTEMD_PID",
        )

    return ServiceState(
        load=values["LoadState"],
        active=values["ActiveState"],
        sub=values["SubState"],
        pid=int(values["MainPID"]),
        control_pid=int(values["ControlPID"]),
        unit_file=values["UnitFileState"],
    )


def read_service():

    command = [
        "systemctl",
        "show",
        "--all",
        "--no-pager",
    ]

    command.extend(
        "-p" + name
        for name in PROPERTIES
    )

    command.append(UNIT)

    try:

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )

    except (OSError, subprocess.TimeoutExpired):

        raise HealthError(
            "SYSTEMD_UNAVAILABLE"
        ) from None

    state = parse_service(result.stdout)

    # Una unidad eliminada por el wrapper
    # puede aparecer como not-found.

    require(
        result.returncode == 0
        or (
            result.returncode == 1
            and state.load == "not-found"
            and (
                state.stopped or state.failed_stop
            )
        ),
        "SYSTEMD_QUERY_FAILED",
    )

    return state


def find_tvheadend_processes():
    """Detecta procesos Tvheadend, incluso fuera de la unidad."""

    matches = []

    for entry in Path("/proc").iterdir():

        if not entry.name.isdecimal():
            continue

        try:

            name = (
                entry / "comm"
            ).read_text().strip()

        except (FileNotFoundError, ProcessLookupError):

            continue

        try:

            executable = os.readlink(
                entry / "exe"
            )

        except (FileNotFoundError, ProcessLookupError):

            executable = ""

        basename = os.path.basename(
            executable.removesuffix(" (deleted)")
        )

        if (
            name == "tvheadend"
            or basename == "tvheadend"
        ):

            matches.append(int(entry.name))

    return tuple(sorted(matches))


def is_stopped(
    read_state=read_service,
    scan_processes=find_tvheadend_processes,
):
    """Confirma unidad detenida, deshabilitada y sin procesos."""

    try:

        before = read_state()

        if not before.stopped:
            return False

        if scan_processes():
            return False

        after = read_state()

        return (
            after == before
            and after.stopped
        )

    except Exception:

        return False


def process_token(pid, binary=BINARY):

    require(
        type(pid) is int and pid > 0,
        "INVALID_PROCESS_PID",
    )

    proc = Path("/proc") / str(pid)

    raw = (
        proc / "stat"
    ).read_text()

    # El nombre del proceso puede contener
    # espacios y parentesis.

    fields = raw[
        raw.rfind(")") + 1:
    ].split()

    require(
        len(fields) > 19,
        "INVALID_PROCESS_STAT",
    )

    started = int(fields[19])

    current = (proc / "exe").stat()
    installed = Path(binary).stat()

    require(
        (
            current.st_dev,
            current.st_ino,
        ) == (
            installed.st_dev,
            installed.st_ino,
        ),
        "RUNNING_BINARY_MISMATCH",
    )

    return (
        pid,
        started,
        current.st_dev,
        current.st_ino,
        current.st_size,
        current.st_mtime_ns,
        current.st_ctime_ns,
    )


def prove_process(pid, binary=BINARY):

    before = process_token(pid, binary)

    path = (
        Path("/proc") / str(pid) / "exe"
    )

    digest = hashlib.sha256()

    with path.open("rb") as stream:

        for chunk in iter(
            lambda: stream.read(256 * 1024),
            b"",
        ):

            digest.update(chunk)

    after = process_token(pid, binary)

    require(
        before == after,
        "PROCESS_CHANGED_DURING_HASH",
    )

    return before, digest.hexdigest()


def probe_htsp():

    with socket.create_connection(
        ("127.0.0.1", HTSP_PORT),
        timeout=HTSP_TIMEOUT,
    ):

        return True


def verify_running(
    expected_sha256,
    api_get,
    *,
    read_state=read_service,
    prove=prove_process,
    token=process_token,
    htsp_probe=probe_htsp,
    binary=BINARY,
):
    """Verifica el ejecutable real y servicios disponibles.

    api_get: interfaz autenticada existente de masQelec.
    HTSP: prueba TCP, no handshake ni sincronizacion PVR.
    """

    require(
        isinstance(expected_sha256, str)
        and SHA256_PATTERN.fullmatch(
            expected_sha256
        ) is not None,
        "INVALID_EXPECTED_SHA256",
    )

    before = read_state()

    require(
        before.running,
        "SERVICE_NOT_RUNNING",
    )

    try:

        observed_token, observed_sha = prove(
            before.pid,
            binary,
        )

    except (OSError, ValueError):

        raise HealthError(
            "RUNNING_PROCESS_UNAVAILABLE"
        ) from None

    require(
        observed_sha == expected_sha256,
        "RUNNING_BINARY_HASH_MISMATCH",
    )

    try:

        ok, code, data, _ = api_get(
            "serverinfo",
            timeout_s=HTTP_TIMEOUT,
        )

    except Exception:

        raise HealthError(
            "TVH_HTTP_UNAVAILABLE"
        ) from None

    require(
        ok is True
        and code == 200
        and isinstance(data, dict)
        and isinstance(
            data.get("sw_version"), str
        )
        and bool(data["sw_version"].strip()),
        "TVH_HTTP_NOT_CONFIRMED",
    )

    try:

        listening = htsp_probe()

    except OSError:

        raise HealthError(
            "TVH_HTSP_UNAVAILABLE"
        ) from None

    require(
        listening is True,
        "TVH_HTSP_NOT_CONFIRMED",
    )

    after = read_state()

    require(
        after == before
        and after.running,
        "SERVICE_STATE_CHANGED",
    )

    try:

        final_token = token(
            after.pid,
            binary,
        )

    except (OSError, ValueError):

        raise HealthError(
            "RUNNING_PROCESS_UNAVAILABLE"
        ) from None

    require(
        final_token == observed_token,
        "PROCESS_IDENTITY_CHANGED",
    )

    return {
        "pid": before.pid,
        "binary_sha256": observed_sha,
        "sw_version": data["sw_version"],
        "http": "PASS",
        "htsp_tcp": "PASS",
        "health": "PASS",
    }
