# -*- coding: utf-8 -*-

import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_backup as backup
from lib import tvheadend_restore as restore


def stopped():
    return True


class TvheadendRestoreTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        userdata = self.base / "addon_data"
        userdata.mkdir()

        self.source = userdata / backup.ADDON_ID
        self.source.mkdir()

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        self.config = self.source / "config"
        self.config.write_text("original")

        channels = self.source / "channel"
        channels.mkdir()

        (channels / "uuid-test").write_text(
            '{"number":1}'
        )

        result = backup.create_backup(
            self.source,
            self.root,
            stopped,
        )

        self.expected = result["tree_sha256"]

        self.config.write_text("modified")

        (channels / "new-uuid").write_text(
            '{"number":2}'
        )

        self.saved = self.root / "config-backup"

        self.displaced = (
            self.root / "config-restore/data"
        )

    def recover(
        self,
        callback=stopped,
        expected=None,
    ):

        return restore.restore_configuration(
            self.source,
            self.root,
            expected or self.expected,
            callback,
        )

    def test_complete_restore(self):

        result = self.recover()

        self.assertEqual(
            result, restore.RESTORED
        )

        self.assertEqual(
            self.config.read_text(),
            "original",
        )

        self.assertFalse(
            (
                self.source / "channel/new-uuid"
            ).exists()
        )

        self.assertEqual(
            (
                self.displaced / "config"
            ).read_text(),
            "modified",
        )

        self.assertTrue(
            (
                self.displaced / "channel/new-uuid"
            ).exists()
        )

    def test_original_backup_preserved(self):

        self.recover()

        result = backup.verify_backup(
            self.saved
        )

        self.assertEqual(
            result["tree_sha256"],
            self.expected,
        )

    def test_restore_is_idempotent(self):

        self.recover()

        with mock.patch.object(
            restore.transaction,
            "atomic_exchange",
        ) as exchange:

            result = self.recover()

        exchange.assert_not_called()

        self.assertEqual(
            result,
            restore.ALREADY_RESTORED,
        )

    def test_running_service_blocks_restore(self):

        with self.assertRaisesRegex(
            restore.RestoreError,
            "^SERVICE_STOP_NOT_CONFIRMED$",
        ):

            self.recover(lambda: False)

        self.assertEqual(
            self.config.read_text(),
            "modified",
        )

    def test_wrong_backup_identity(self):

        with self.assertRaisesRegex(
            restore.RestoreError,
            "^RESTORE_BACKUP_IDENTITY_MISMATCH$",
        ):

            self.recover(
                expected="0" * 64
            )

    def test_corrupted_backup_rejected(self):

        (
            self.saved / "data/config"
        ).write_text("corrupted")

        with self.assertRaisesRegex(
            backup.BackupError,
            "^BACKUP_INTEGRITY_MISMATCH$",
        ):

            self.recover()

        self.assertEqual(
            self.config.read_text(),
            "modified",
        )

    def test_interruption_before_exchange(self):

        with mock.patch.object(
            restore.transaction,
            "atomic_exchange",
            side_effect=OSError(
                "simulated interruption"
            ),
        ):

            with self.assertRaises(OSError):
                self.recover()

        self.assertEqual(
            self.config.read_text(),
            "modified",
        )

        self.assertTrue(
            self.displaced.is_dir()
        )

        self.assertEqual(
            self.recover(),
            restore.RESTORED,
        )

    def test_interruption_after_exchange(self):

        original = (
            restore.transaction.atomic_exchange
        )

        def interrupted(left, right):

            original(left, right)

            raise OSError(
                "simulated interruption"
            )

        with mock.patch.object(
            restore.transaction,
            "atomic_exchange",
            side_effect=interrupted,
        ):

            with self.assertRaises(OSError):
                self.recover()

        self.assertEqual(
            self.config.read_text(),
            "original",
        )

        self.assertEqual(
            self.recover(),
            restore.ALREADY_RESTORED,
        )

    def test_unexpected_candidate_preserved(self):

        self.displaced.mkdir(
            parents=True,
            mode=0o700,
        )

        self.displaced.parent.chmod(0o700)

        marker = self.displaced / "marker"

        marker.write_text(
            "unexpected existing data"
        )

        with self.assertRaisesRegex(
            restore.RestoreError,
            "^RESTORE_CANDIDATE_MISMATCH$",
        ):

            self.recover()

        self.assertEqual(
            marker.read_text(),
            "unexpected existing data",
        )

        self.assertEqual(
            self.config.read_text(),
            "modified",
        )

    def test_copy_failure_preserves_source(self):

        with mock.patch.object(
            backup,
            "copy_inventory",
            side_effect=OSError(
                "simulated copy failure"
            ),
        ):

            with self.assertRaises(OSError):
                self.recover()

        self.assertEqual(
            self.config.read_text(),
            "modified",
        )

        self.assertFalse(
            self.displaced.parent.exists()
        )

        self.assertEqual(
            list(
                self.root.glob(
                    ".config-restore-*"
                )
            ),
            [],
        )

    def test_service_restart_blocks_exchange(self):

        callback = mock.Mock(
            side_effect=[True, True, False]
        )

        with mock.patch.object(
            restore.transaction,
            "atomic_exchange",
        ) as exchange:

            with self.assertRaisesRegex(
                restore.RestoreError,
                "^SERVICE_STOP_NOT_CONFIRMED$",
            ):

                self.recover(callback)

        exchange.assert_not_called()

        self.assertEqual(
            self.config.read_text(),
            "modified",
        )


if __name__ == "__main__":
    unittest.main()
