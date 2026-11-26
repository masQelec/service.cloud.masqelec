# -*- coding: utf-8 -*-
"""Instalacion persistente del protector de arranque TVH.

No reinicia Kodi ni Tvheadend.
No modifica unidades originales ni ficheros de rclone.
"""

import os
import stat
import subprocess

from pathlib import Path

from lib import tvheadend_boot as boot
from lib import rclone_two_mount_atomic_install as atomic


SYSTEMD_DIR = Path("/storage/.config/system.d")

RUNNER = (
    boot.ADDON_ROOT
    / "tools/tvheadend_early_boot_run.py"
)


class BootInstallError(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise BootInstallError(code)


def is_coreelec_root():

    if os.geteuid() != 0:
        return False

    try:

        release = Path(
            "/etc/os-release"
        ).read_text()

        return any(
            line.strip() in (
                "ID=coreelec",
                'ID="coreelec"',
            )
            for line in release.splitlines()
        )

    except OSError:
        return False


def systemctl(*args):

    result = subprocess.run(
        ["systemctl", *args],
        capture_output=True,
        text=True,
        timeout=190,
        check=False,
    )

    require(
        result.returncode == 0,
        "BOOT_SYSTEMCTL_FAILED",
    )

    return result.stdout


def verify_existing(path, expected):

    info = path.lstat()

    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and not info.st_mode & 0o022
        and info.st_size == len(expected),
        "BOOT_INSTALL_CONFLICT",
    )

    fd = os.open(
        path,
        os.O_RDONLY | os.O_NOFOLLOW,
    )

    try:

        require(
            os.read(fd, len(expected) + 1)
            == expected,
            "BOOT_INSTALL_CONFLICT",
        )

    finally:
        os.close(fd)


def install_files(folder, runner):

    folder = Path(folder)
    runner = Path(runner)

    require(
        folder.is_absolute()
        and folder.resolve() == folder,
        "UNSAFE_SYSTEMD_DIRECTORY",
    )

    atomic._trusted_folder(str(folder))

    require(
        runner.is_file()
        and runner.resolve() == runner
        and runner.stat().st_size > 0,
        "BOOT_RUNNER_MISSING",
    )

    kodi_dir = folder / "kodi.service.d"

    tvh_dir = (
        folder / "service.tvheadend43.service.d"
    )

    artifacts = (
        (
            folder / boot.UNIT_NAME,
            boot.UNIT.encode("ascii"),
        ),
        (
            kodi_dir / boot.DROPIN_NAME,
            boot.KODI_DROPIN.encode("ascii"),
        ),
        (
            tvh_dir / boot.DROPIN_NAME,
            boot.TVH_DROPIN.encode("ascii"),
        ),
        (
            tvh_dir / boot.STOP_DROPIN_NAME,
            boot.STOP_DROPIN.encode("ascii"),
        ),
    )

    # Validar todo antes de escribir nada.

    for directory in (kodi_dir, tvh_dir):

        if os.path.lexists(directory):

            atomic._trusted_folder(
                str(directory)
            )

    for path, expected in artifacts:

        if os.path.lexists(path):

            verify_existing(path, expected)

    # Primero la unidad de recuperacion.
    # La dependencia obligatoria TVH se instala
    # siempre despues de la unidad.

    for path, expected in artifacts:

        parent = path.parent

        if not os.path.lexists(parent):

            parent.mkdir(mode=0o755)

            atomic._fsync_dir(
                str(parent.parent)
            )

        atomic._trusted_folder(str(parent))

        if not os.path.lexists(path):

            atomic.install_exclusive(
                str(path),
                expected,
                0o644,
            )

        verify_existing(path, expected)

    return "FILES_INSTALLED"


def properties(ctl, unit, *names):

    raw = ctl(
        "show",
        "--all",
        "--no-pager",
        *("-p" + name for name in names),
        unit,
    )

    require(
        isinstance(raw, str)
        and len(raw) <= 65536,
        "INVALID_SYSTEMD_PROPERTIES",
    )

    result = {}

    for line in raw.splitlines():

        if not line:
            continue

        key, sep, value = line.partition("=")

        require(
            sep == "="
            and key in names
            and key not in result,
            "INVALID_SYSTEMD_PROPERTIES",
        )

        result[key] = value

    require(
        set(result) == set(names),
        "INCOMPLETE_SYSTEMD_PROPERTIES",
    )

    return result


def verify_dependencies(ctl=systemctl):

    kodi = properties(
        ctl,
        boot.KODI_UNIT,
        "LoadState",
        "Wants",
        "Requires",
        "After",
    )

    tvh = properties(
        ctl,
        boot.TVH_UNIT,
        "LoadState",
        "Requires",
        "After",
    )

    recovery = properties(
        ctl,
        boot.UNIT_NAME,
        "LoadState",
        "Before",
        "Type",
        "RemainAfterExit",
    )

    name = boot.UNIT_NAME

    require(
        kodi["LoadState"] == "loaded"
        and tvh["LoadState"] == "loaded"
        and recovery["LoadState"] == "loaded",
        "BOOT_UNIT_NOT_LOADED",
    )

    require(
        name in kodi["Wants"].split()
        and name in kodi["After"].split()
        and name not in kodi["Requires"].split(),
        "KODI_BOOT_DEPENDENCY_MISMATCH",
    )

    require(
        name in tvh["Requires"].split()
        and name in tvh["After"].split(),
        "TVH_BOOT_DEPENDENCY_MISMATCH",
    )

    require(
        boot.KODI_UNIT in recovery["Before"].split()
        and boot.TVH_UNIT in recovery["Before"].split()
        and recovery["Type"] == "oneshot"
        and recovery["RemainAfterExit"] == "yes",
        "RECOVERY_UNIT_MISMATCH",
    )

    return True


def verify_stop_timeout(ctl=systemctl):

    state = properties(
        ctl,
        boot.TVH_UNIT,
        "TimeoutStopUSec",
    )

    require(
        state["TimeoutStopUSec"] in (
            "1min", "60s", "1min 0s"
        ),
        "TVH_STOP_TIMEOUT_NOT_CONFIRMED",
    )

    return True


def recovery_ready(ctl=systemctl):

    state = properties(
        ctl,
        boot.UNIT_NAME,
        "ActiveState",
        "SubState",
        "Result",
    )

    return (
        state["ActiveState"] == "active"
        and state["SubState"] == "exited"
        and state["Result"] == "success"
    )


def ensure_installed(
    *,
    authorized=False,
    folder=SYSTEMD_DIR,
    runner=RUNNER,
    transaction_root=boot.TRANSACTION_ROOT,
    ctl=systemctl,
):

    require(
        authorized is True,
        "BOOT_INSTALL_NOT_AUTHORIZED",
    )

    require(
        is_coreelec_root(),
        "BOOT_INSTALL_PLATFORM_REJECTED",
    )

    root = Path(transaction_root)

    # No activar una recuperacion nueva con Kodi
    # funcionando si existe una transaccion pendiente.

    require(
        root.is_absolute()
        and root.resolve() == root,
        "UNSAFE_TRANSACTION_ROOT",
    )

    for name in ("update.json", "journal.json"):

        require(
            not os.path.lexists(root / name),
            "BOOT_INSTALL_PENDING_TRANSACTION",
        )

    install_files(folder, runner)

    ctl("daemon-reload")

    verify_dependencies(ctl)

    if not recovery_ready(ctl):

        # Con ningun journal pendiente, el runner
        # devuelve NO_PENDING sin modificar TVH.

        ctl("start", boot.UNIT_NAME)

    require(
        recovery_ready(ctl),
        "RECOVERY_UNIT_NOT_READY",
    )

    return "READY"
