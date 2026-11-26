# -*- coding: utf-8 -*-
"""Activacion offline y prueba de proteccion por arranque.

Un fallo de politica impide nuevas actualizaciones,
pero no debe impedir el funcionamiento de TVH.
"""

import os
import stat
import uuid

from pathlib import Path

from lib import tvheadend_boot as boot
from lib import tvheadend_boot_install as install
from lib import tvheadend_lifecycle as lifecycle
from lib import tvheadend_backup as backup
from lib import tvheadend_update_policy as policy
from lib import rclone_two_mount_atomic_install as atomic


MARKER = Path("/run/masqelec-tvh-policy-ready")

BACKUP_DIRECTORY = "tvheadend-policy-backups"

KODI_PROCESSES = {"kodi", "kodi.bin"}


class BootPolicyError(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise BootPolicyError(code)


def current_boot_id():

    value = Path(
        "/proc/sys/kernel/random/boot_id"
    ).read_text().strip()

    require(
        str(uuid.UUID(value)) == value,
        "INVALID_BOOT_ID",
    )

    return value


def kodi_processes():

    found = []

    for process in Path("/proc").iterdir():

        if not process.name.isdecimal():
            continue

        try:

            name = (
                process / "comm"
            ).read_text().strip()

            if name in KODI_PROCESSES:

                found.append(int(process.name))
                continue

            try:

                executable = os.readlink(
                    process / "exe"
                )

            except FileNotFoundError:

                continue

            executable = executable.removesuffix(
                " (deleted)"
            )

            if Path(executable).name in KODI_PROCESSES:

                found.append(int(process.name))

        except FileNotFoundError:

            continue

    return tuple(found)


def boot_context():

    """Exige el contexto de ejecucion de la unidad real."""

    try:

        if not install.is_coreelec_root():
            return False

        if not install.verify_dependencies():
            return False

        state = install.properties(
            install.systemctl,
            boot.UNIT_NAME,
            "ActiveState",
            "MainPID",
            "ControlPID",
        )

        return (
            state["ActiveState"] == "activating"
            and str(os.getpid()) in (
                state["MainPID"],
                state["ControlPID"],
            )
            and boot.boot_quiescent()
            and not kodi_processes()
        )

    except Exception:

        return False


def marker_payload(database, boot_id):

    path = policy.validate_database(database)

    require(
        str(uuid.UUID(boot_id)) == boot_id,
        "INVALID_BOOT_ID",
    )

    info = path.stat()

    return (
        "schema=1\n"
        f"boot_id={boot_id}\n"
        f"database_device={info.st_dev}\n"
        f"database_inode={info.st_ino}\n"
        "addon=service.tvheadend43\n"
        "rule=1\n"
    ).encode("ascii")


def validate_marker_parent(marker):

    require(
        marker.is_absolute()
        and marker.parent.resolve() == marker.parent,
        "UNSAFE_POLICY_MARKER_PATH",
    )

    atomic._trusted_folder(
        str(marker.parent)
    )


def clear_marker(marker):

    validate_marker_parent(marker)

    if not os.path.lexists(marker):
        return

    info = marker.lstat()

    require(
        stat.S_ISREG(info.st_mode)
        and info.st_uid == os.geteuid()
        and info.st_nlink == 1
        and stat.S_IMODE(info.st_mode) == 0o600,
        "UNSAFE_POLICY_MARKER",
    )

    marker.unlink()

    atomic._fsync_dir(
        str(marker.parent)
    )


def policy_ready(
    database=policy.DATABASE,
    marker=MARKER,
    read_boot_id=current_boot_id,
):
    """Verifica evidencia del arranque y regla persistente."""

    try:

        marker = Path(marker)

        validate_marker_parent(marker)

        fd = os.open(
            marker,
            os.O_RDONLY
            | os.O_NOFOLLOW
            | os.O_NONBLOCK,
        )

        try:

            info = os.fstat(fd)

            require(
                stat.S_ISREG(info.st_mode)
                and info.st_uid == os.geteuid()
                and info.st_nlink == 1
                and stat.S_IMODE(info.st_mode) == 0o600
                and 0 < info.st_size <= 512,
                "UNSAFE_POLICY_MARKER",
            )

            observed = os.read(fd, 513)

        finally:

            os.close(fd)

        expected = marker_payload(
            database,
            read_boot_id(),
        )

        if observed != expected:

            return False

        return policy.inspect_policy(
            database
        ) is True

    except Exception:

        return False


def activate_at_boot(
    *,
    root=boot.TRANSACTION_ROOT,
    database=policy.DATABASE,
    marker=MARKER,
    read_boot_id=current_boot_id,
    assert_context=boot_context,
):
    """Solo se invoca desde la recuperacion temprana."""

    root = Path(root)
    marker = Path(marker)

    manager = lifecycle.Lifecycle(root)

    with manager.locked():

        # No reutilizar una confirmacion anterior
        # si esta ejecucion no puede acreditar el contexto.

        clear_marker(marker)

        if assert_context() is not True:

            return "DEFERRED_BOOT_CONTEXT"

        boot_id = read_boot_id()

        expected = marker_payload(
            database, boot_id
        )

        folder = (
            root.parent / BACKUP_DIRECTORY
        )

        if not os.path.lexists(folder):

            folder.mkdir(mode=0o700)

            atomic._fsync_dir(
                str(folder.parent)
            )

        backup.validate_private(folder)

        result = policy.ensure_offline_policy(
            database,
            folder,
            assert_context,
            authorized=True,
        )

        require(
            result in (
                "PROTECTED",
                "ALREADY_PROTECTED",
            ),
            "POLICY_ACTIVATION_UNCONFIRMED",
        )

        require(
            assert_context() is True,
            "BOOT_CONTEXT_LOST",
        )

        require(
            marker_payload(database, read_boot_id())
            == expected,
            "POLICY_DATABASE_CHANGED",
        )

        atomic.install_exclusive(
            str(marker),
            expected,
            0o600,
        )

        if not policy_ready(
            database, marker, read_boot_id
        ):

            clear_marker(marker)

            raise BootPolicyError(
                "POLICY_MARKER_UNCONFIRMED"
            )

        return result
