# -*- coding: utf-8 -*-

import sqlite3
import tempfile
import unittest

from contextlib import closing
from pathlib import Path
from unittest import mock

from lib import tvheadend_boot_policy as boot
from lib import tvheadend_update_policy as policy


BOOT_ID = "9fc927cb-4789-4a90-9e64-123456789abc"

NEXT_BOOT_ID = "9fc927cb-4789-4a90-9e64-123456789abd"


class TvheadendBootPolicyTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        self.root = self.base / "transaction"

        self.marker = self.base / "policy-ready"

        self.db = self.base / "Addons33.db"

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
        """)

    def sql(self, script):

        with closing(
            sqlite3.connect(self.db)
        ) as conn:

            conn.executescript(script)
            conn.commit()

    def activate(self, guard=lambda: True):

        return boot.activate_at_boot(
            root=self.root,
            database=self.db,
            marker=self.marker,
            read_boot_id=lambda: BOOT_ID,
            assert_context=guard,
        )

    def ready(self, boot_id=BOOT_ID):

        return boot.policy_ready(
            self.db,
            self.marker,
            lambda: boot_id,
        )

    def test_offline_activation(self):

        self.assertEqual(
            self.activate(),
            "PROTECTED",
        )

        self.assertTrue(self.ready())

        self.assertTrue(
            policy.inspect_policy(self.db)
        )

        self.assertEqual(
            self.marker.stat().st_mode & 0o777,
            0o600,
        )

    def test_running_kodi_defers_activation(self):

        self.assertEqual(
            self.activate(lambda: False),
            "DEFERRED_BOOT_CONTEXT",
        )

        self.assertFalse(self.ready())

        self.assertFalse(
            policy.inspect_policy(self.db)
        )

        self.assertFalse(self.marker.exists())

    def test_database_rule_alone_is_insufficient(self):

        self.sql("""
            INSERT INTO update_rules
                (addonID, updateRule)
            VALUES ('service.tvheadend43', 1);
        """)

        self.assertTrue(
            policy.inspect_policy(self.db)
        )

        self.assertFalse(self.ready())

    def test_marker_from_previous_boot_rejected(self):

        self.activate()

        self.assertFalse(
            self.ready(NEXT_BOOT_ID)
        )

    def test_removed_rule_blocks_updates(self):

        self.activate()

        self.sql("""
            DELETE FROM update_rules
            WHERE addonID = 'service.tvheadend43';
        """)

        self.assertFalse(self.ready())

    def test_policy_failure_leaves_no_marker(self):

        with mock.patch.object(
            policy,
            "ensure_offline_policy",
            side_effect=OSError("synthetic failure"),
        ):

            with self.assertRaises(OSError):

                self.activate()

        self.assertFalse(self.marker.exists())
        self.assertFalse(self.ready())

    def test_invalid_reactivation_invalidates_marker(self):

        self.activate()

        self.assertTrue(self.ready())

        self.assertEqual(
            self.activate(lambda: False),
            "DEFERRED_BOOT_CONTEXT",
        )

        self.assertFalse(self.ready())

        self.assertTrue(
            policy.inspect_policy(self.db)
        )

    def test_symlink_marker_rejected(self):

        self.marker.symlink_to(self.db)

        self.assertFalse(self.ready())

        with self.assertRaisesRegex(
            boot.BootPolicyError,
            "^UNSAFE_POLICY_MARKER$",
        ):

            self.activate()

        self.assertTrue(self.marker.is_symlink())
        self.assertTrue(self.db.is_file())


if __name__ == "__main__":
    unittest.main()
