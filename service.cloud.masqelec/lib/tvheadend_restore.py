# -*- coding: utf-8 -*-
"""Restauracion atomica de configuracion Tvheadend.

Requiere servicio detenido y bloqueo exclusivo externo.
Conserva el respaldo original y la configuracion desplazada.
No controla Kodi ni systemd.
"""

import os
import shutil
import tempfile

from pathlib import Path

from lib import tvheadend_backup as backup
from lib import tvheadend_transaction as transaction


RESTORED = "RESTORED"
ALREADY_RESTORED = "ALREADY_RESTORED"


class RestoreError(RuntimeError):
    """Restauracion bloqueada o no confirmada."""


def require(condition, code):

    if not condition:
        raise RestoreError(code)


def require_stopped(assert_stopped):

    require(
        assert_stopped() is True,
        "SERVICE_STOP_NOT_CONFIRMED",
    )


def restore_configuration(
    source_path,
    transaction_root,
    expected_tree_sha256,
    assert_stopped,
):
    """Restaura una copia verificada del respaldo original.

    El hash esperado debe proceder del journal del
    coordinador, no de metadatos recibidos de Internet.

    El llamador mantiene el bloqueo durante toda
    la operacion y durante la recuperacion posterior.
    """

    source = Path(source_path)
    root = Path(transaction_root)

    backup.validate_directory(source)
    backup.validate_private(root)

    require(
        source.name == backup.ADDON_ID,
        "INVALID_RESTORE_SOURCE",
    )

    require(
        source != root
        and source not in root.parents
        and root not in source.parents,
        "RESTORE_PATH_OVERLAP",
    )

    require(
        source.stat().st_dev == root.stat().st_dev,
        "RESTORE_FILESYSTEM_MISMATCH",
    )

    require_stopped(assert_stopped)

    saved = root / "config-backup"

    expected = backup.verify_backup(saved)

    require(
        expected["tree_sha256"]
        == expected_tree_sha256,
        "RESTORE_BACKUP_IDENTITY_MISMATCH",
    )

    records, observed_backup = backup.inventory(
        saved / "data"
    )

    require(
        observed_backup == expected,
        "RESTORE_BACKUP_CHANGED",
    )

    _, current = backup.inventory(source)

    restore_root = root / "config-restore"

    # Si el intercambio ya se produjo antes de
    # una interrupcion, no volver a intercambiar.

    if current == expected:

        require_stopped(assert_stopped)

        transaction.sync_directory(source.parent)

        if os.path.lexists(restore_root):

            backup.validate_private(restore_root)
            transaction.sync_directory(restore_root)

        transaction.sync_directory(root)

        return ALREADY_RESTORED

    if not os.path.lexists(restore_root):

        needed = (
            expected["bytes"]
            + expected["entries"] * 4096
            + backup.FREE_SPACE_RESERVE
        )

        require(
            shutil.disk_usage(root).free >= needed,
            "INSUFFICIENT_RESTORE_SPACE",
        )

        temp = Path(
            tempfile.mkdtemp(
                prefix=".config-restore-",
                dir=root,
            )
        )

        try:

            backup.copy_inventory(
                saved / "data",
                temp / "data",
                records,
            )

            _, copied = backup.inventory(
                temp / "data"
            )

            require(
                copied == expected,
                "RESTORE_COPY_MISMATCH",
            )

            transaction.sync_tree(temp)

            require_stopped(assert_stopped)

            require(
                not os.path.lexists(restore_root),
                "RESTORE_ALREADY_EXISTS",
            )

            os.rename(temp, restore_root)
            transaction.sync_directory(root)

        finally:

            if temp.exists():
                shutil.rmtree(temp)

    backup.validate_private(restore_root)

    candidate = restore_root / "data"

    _, prepared = backup.inventory(candidate)

    require(
        prepared == expected,
        "RESTORE_CANDIDATE_MISMATCH",
    )

    require(
        candidate.stat().st_dev
        == source.stat().st_dev,
        "RESTORE_FILESYSTEM_MISMATCH",
    )

    require(
        not os.path.samefile(source, candidate),
        "IDENTICAL_RESTORE_DIRECTORIES",
    )

    require_stopped(assert_stopped)

    _, latest = backup.inventory(source)

    require(
        latest == current,
        "RESTORE_SOURCE_CHANGED",
    )

    require_stopped(assert_stopped)

    transaction.atomic_exchange(
        source,
        candidate,
    )

    _, restored = backup.inventory(source)

    require(
        restored == expected,
        "RESTORE_NOT_CONFIRMED",
    )

    _, displaced = backup.inventory(candidate)

    require(
        displaced == current,
        "DISPLACED_CONFIG_MISMATCH",
    )

    require_stopped(assert_stopped)

    return RESTORED
