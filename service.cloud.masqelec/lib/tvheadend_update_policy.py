# -*- coding: utf-8 -*-
"""Proteccion individual de actualizacion de Tvheadend.

Contrato validado para Kodi 21 / Addons33.db.
Escritura exclusivamente offline y autorizada.
No modifica bases de datos PVR.
"""

import os
import sqlite3
import tempfile

from contextlib import closing
from pathlib import Path

from lib import tvheadend_backup as backup
from lib import tvheadend_transaction as tx


ADDON_ID = "service.tvheadend43"

DATABASE_VERSION = 33
DATABASE_NAME = "Addons33.db"

USER_DISABLED_AUTO_UPDATE = 1

DATABASE = Path(
    "/storage/.kodi/userdata/Database/"
    "Addons33.db"
)

EXPECTED_COLUMNS = (
    (0, "id", "INTEGER", 0, None, 1),
    (1, "addonID", "TEXT", 0, None, 0),
    (2, "updateRule", "INTEGER", 0, None, 0),
)

EXPECTED_INDEX = (
    (0, 1, "addonID"),
    (1, 2, "updateRule"),
)


class PolicyError(RuntimeError):
    pass


def require(condition, code):

    if not condition:
        raise PolicyError(code)


def validate_database(path):

    path = Path(path)

    require(
        path.is_absolute()
        and path.resolve() == path
        and path.name == DATABASE_NAME
        and path.is_file(),
        "UNSUPPORTED_ADDON_DATABASE",
    )

    return path


def connect(path, mode):

    return sqlite3.connect(
        path.as_uri() + "?mode=" + mode,
        uri=True,
        timeout=5,
        isolation_level=None,
    )


def check_integrity(conn):

    require(
        conn.execute(
            "PRAGMA integrity_check"
        ).fetchall() == [("ok",)],
        "ADDON_DATABASE_INTEGRITY_FAILED",
    )


def validate_schema(conn):

    versions = conn.execute(
        "SELECT idVersion FROM version"
    ).fetchall()

    require(
        versions == [(DATABASE_VERSION,)],
        "ADDON_DATABASE_VERSION_MISMATCH",
    )

    columns = tuple(
        conn.execute(
            "PRAGMA table_info(update_rules)"
        )
    )

    require(
        columns == EXPECTED_COLUMNS,
        "UPDATE_RULE_COLUMNS_MISMATCH",
    )

    indexes = list(
        conn.execute(
            "PRAGMA index_list(update_rules)"
        )
    )

    require(
        any(
            row[1:] == (
                "idxUpdate_rules",
                1,
                "c",
                0,
            )
            for row in indexes
        ),
        "UPDATE_RULE_UNIQUE_INDEX_MISSING",
    )

    index_columns = tuple(
        conn.execute(
            "PRAGMA index_info(idxUpdate_rules)"
        )
    )

    require(
        index_columns == EXPECTED_INDEX,
        "UPDATE_RULE_INDEX_MISMATCH",
    )

    triggers = conn.execute(
        """
        SELECT name FROM sqlite_master
        WHERE type = 'trigger'
          AND lower(tbl_name) = 'update_rules'
        """
    ).fetchall()

    require(
        not triggers,
        "UNEXPECTED_UPDATE_RULE_TRIGGERS",
    )


def rules_snapshot(conn):

    return conn.execute(
        """
        SELECT id, addonID, updateRule
        FROM update_rules
        ORDER BY id
        """
    ).fetchall()


def protected(conn):

    result = conn.execute(
        """
        SELECT COUNT(*)
        FROM update_rules
        WHERE addonID = ?
          AND updateRule = ?
        """,
        (
            ADDON_ID,
            USER_DISABLED_AUTO_UPDATE,
        ),
    ).fetchone()

    return result == (1,)


def inspect_policy(path=DATABASE):
    """Consulta persistencia, no la cache de Kodi."""

    path = validate_database(path)

    with closing(connect(path, "ro")) as conn:

        conn.execute("PRAGMA query_only=ON")

        validate_schema(conn)

        return protected(conn)


def create_database_backup(path, folder, expected_rules):

    folder = Path(folder)

    backup.validate_private(folder)

    fd, filename = tempfile.mkstemp(
        prefix="Addons33-before-tvh-policy-",
        suffix=".db",
        dir=folder,
    )

    os.close(fd)

    destination = Path(filename)

    try:

        with closing(
            connect(path, "ro")
        ) as source:

            with closing(
                connect(destination, "rw")
            ) as target:

                source.backup(target)

                validate_schema(target)
                check_integrity(target)

                require(
                    rules_snapshot(target)
                    == expected_rules,
                    "POLICY_BACKUP_RULES_MISMATCH",
                )

        with destination.open("rb") as handle:

            os.fsync(handle.fileno())

        tx.sync_directory(folder)

        return destination

    except BaseException:

        destination.unlink(missing_ok=True)

        tx.sync_directory(folder)

        raise


def ensure_offline_policy(
    path,
    backup_folder,
    assert_quiescent,
    *,
    authorized=False,
):
    """Inserta solo la regla nativa de TVH.

    La llamada real requiere exclusividad de arranque
    systemd y un bloqueo externo estable.
    """

    require(
        authorized is True,
        "POLICY_NOT_AUTHORIZED",
    )

    require(
        assert_quiescent() is True,
        "POLICY_KODI_NOT_QUIESCENT",
    )

    path = validate_database(path)

    backup_folder = Path(backup_folder)

    backup.validate_private(backup_folder)

    with closing(connect(path, "rw")) as conn:

        conn.execute("PRAGMA synchronous=FULL")

        # Reserva la escritura antes de obtener
        # el respaldo consistente.

        conn.execute("BEGIN IMMEDIATE")

        try:

            validate_schema(conn)
            check_integrity(conn)

            if protected(conn):

                conn.execute("ROLLBACK")

                return "ALREADY_PROTECTED"

            previous = rules_snapshot(conn)

            create_database_backup(
                path,
                backup_folder,
                previous,
            )

            require(
                assert_quiescent() is True,
                "POLICY_KODI_NOT_QUIESCENT",
            )

            cursor = conn.execute(
                """
                INSERT INTO update_rules
                    (addonID, updateRule)
                VALUES (?, ?)
                """,
                (
                    ADDON_ID,
                    USER_DISABLED_AUTO_UPDATE,
                ),
            )

            require(
                cursor.rowcount == 1,
                "POLICY_INSERT_COUNT_MISMATCH",
            )

            inserted = (
                cursor.lastrowid,
                ADDON_ID,
                USER_DISABLED_AUTO_UPDATE,
            )

            require(
                rules_snapshot(conn)
                == sorted(previous + [inserted]),
                "UNEXPECTED_UPDATE_RULE_CHANGE",
            )

            require(
                protected(conn),
                "POLICY_NOT_CONFIRMED",
            )

            check_integrity(conn)

            require(
                assert_quiescent() is True,
                "POLICY_KODI_NOT_QUIESCENT",
            )

            conn.execute("COMMIT")

        except BaseException:

            if conn.in_transaction:

                conn.execute("ROLLBACK")

            raise

    require(
        inspect_policy(path) is True,
        "POLICY_PERSISTENCE_NOT_CONFIRMED",
    )

    return "PROTECTED"
