# -*- coding: utf-8 -*-

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path
from unittest import mock

from lib import tvheadend_update_policy as policy


class TvheadendUpdatePolicyTests(
    unittest.TestCase
):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        self.db = self.base / "Addons33.db"

        self.backups = self.base / "backups"
        self.backups.mkdir(mode=0o700)

        self.sql("""
            CREATE TABLE version (
                idVersion INTEGER
            );

            INSERT INTO version VALUES (33);

            CREATE TABLE update_rules (
                id INTEGER PRIMARY KEY,
                addonID TEXT,
                updateRule INTEGER
            );

            CREATE UNIQUE INDEX idxUpdate_rules
            ON update_rules(addonID, updateRule);

            INSERT INTO update_rules
                (addonID, updateRule)
            VALUES ('other.addon', 2);

            INSERT INTO update_rules
                (addonID, updateRule)
            VALUES ('service.tvheadend43', 3);
        """)

    def sql(self, script):

        with closing(
            sqlite3.connect(self.db)
        ) as conn:

            conn.executescript(script)
            conn.commit()

    def rows(self, path=None):

        with closing(
            sqlite3.connect(path or self.db)
        ) as conn:

            return policy.rules_snapshot(conn)

    def ensure(
        self,
        authorized=True,
        quiescent=lambda: True,
    ):

        return policy.ensure_offline_policy(
            self.db,
            self.backups,
            quiescent,
            authorized=authorized,
        )

    def test_apply_policy_preserves_other_rules(self):

        previous = self.rows()

        self.assertEqual(
            self.ensure(),
            "PROTECTED",
        )

        current = self.rows()

        self.assertEqual(
            current[:len(previous)],
            previous,
        )

        self.assertEqual(
            current[-1][1:],
            (
                "service.tvheadend43",
                1,
            ),
        )

        self.assertTrue(
            policy.inspect_policy(self.db)
        )

    def test_idempotent_policy(self):

        self.ensure()

        previous = self.rows()

        self.assertEqual(
            self.ensure(),
            "ALREADY_PROTECTED",
        )

        self.assertEqual(
            self.rows(), previous
        )

        self.assertEqual(
            len(list(self.backups.iterdir())),
            1,
        )

    def test_consistent_backup(self):

        previous = self.rows()

        self.ensure()

        files = list(self.backups.iterdir())

        self.assertEqual(len(files), 1)

        self.assertEqual(
            self.rows(files[0]),
            previous,
        )

        self.assertFalse(
            files[0].stat().st_mode & 0o077
        )

    def test_unauthorized_blocks(self):

        previous = self.rows()

        with self.assertRaisesRegex(
            policy.PolicyError,
            "^POLICY_NOT_AUTHORIZED$",
        ):

            self.ensure(False)

        self.assertEqual(
            self.rows(), previous
        )

        self.assertEqual(
            list(self.backups.iterdir()),
            [],
        )

    def test_running_kodi_blocks(self):

        previous = self.rows()

        with self.assertRaisesRegex(
            policy.PolicyError,
            "^POLICY_KODI_NOT_QUIESCENT$",
        ):

            self.ensure(
                quiescent=lambda: False
            )

        self.assertEqual(
            self.rows(), previous
        )

    def test_quiescence_lost_before_commit(self):

        previous = self.rows()

        guard = mock.Mock(
            side_effect=[
                True,
                True,
                False,
            ]
        )

        with self.assertRaisesRegex(
            policy.PolicyError,
            "^POLICY_KODI_NOT_QUIESCENT$",
        ):

            self.ensure(quiescent=guard)

        self.assertEqual(
            self.rows(), previous
        )

        self.assertFalse(
            policy.inspect_policy(self.db)
        )

    def test_wrong_database_version_blocks(self):

        self.sql(
            "UPDATE version SET idVersion=34;"
        )

        with self.assertRaisesRegex(
            policy.PolicyError,
            "^ADDON_DATABASE_VERSION_MISMATCH$",
        ):

            self.ensure()

    def test_missing_unique_index_blocks(self):

        self.sql(
            "DROP INDEX idxUpdate_rules;"
        )

        with self.assertRaisesRegex(
            policy.PolicyError,
            "^UPDATE_RULE_UNIQUE_INDEX_MISSING$",
        ):

            self.ensure()

    def test_unexpected_trigger_blocks(self):

        self.sql("""
            CREATE TRIGGER unexpected
            AFTER INSERT ON update_rules
            BEGIN
                DELETE FROM update_rules
                WHERE addonID = 'other.addon';
            END;
        """)

        previous = self.rows()

        with self.assertRaisesRegex(
            policy.PolicyError,
            "^UNEXPECTED_UPDATE_RULE_TRIGGERS$",
        ):

            self.ensure()

        self.assertEqual(
            self.rows(), previous
        )

    def test_backup_failure_blocks_insert(self):

        previous = self.rows()

        with mock.patch.object(
            policy,
            "create_database_backup",
            side_effect=OSError("backup failed"),
        ):

            with self.assertRaises(OSError):

                self.ensure()

        self.assertEqual(
            self.rows(), previous
        )


if __name__ == "__main__":
    unittest.main()
