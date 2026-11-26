# -*- coding: utf-8 -*-

import os
import stat
import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_backup as backup


class TvheadendBackupTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        self.source = (
            self.base / backup.ADDON_ID
        )

        self.source.mkdir()

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        self.final = self.root / "config-backup"

        self.config = self.source / "config"

        self.config.write_text(
            '{"test":true}'
        )

        self.channel = (
            self.source / "channel"
        )

        self.channel.mkdir()

        (self.channel / "uuid-test").write_text(
            '{"number":1}'
        )

        (self.source / "empty").mkdir()

    def create(self, stopped=lambda: True):

        return backup.create_backup(
            self.source,
            self.root,
            stopped,
        )

    def rejected(
        self, code, stopped=lambda: True
    ):

        with self.assertRaisesRegex(
            backup.BackupError,
            "^" + code + "$",
        ):

            self.create(stopped)

    def test_complete_backup(self):

        result = self.create()

        self.assertEqual(
            result["files"], 2
        )

        self.assertEqual(
            result["path"], self.final
        )

        original, _ = backup.inventory(
            self.source
        )

        copied, _ = backup.inventory(
            self.final / "data"
        )

        self.assertEqual(
            original, copied
        )

        self.assertEqual(
            backup.verify_backup(
                self.final
            )["tree_sha256"],
            result["tree_sha256"],
        )

    def test_permissions_and_empty_directories(self):

        self.config.chmod(0o640)
        self.channel.chmod(0o750)

        self.create()

        data = self.final / "data"

        self.assertTrue(
            (data / "empty").is_dir()
        )

        self.assertEqual(
            stat.S_IMODE(
                (data / "config").stat().st_mode
            ),
            0o640,
        )

        self.assertEqual(
            stat.S_IMODE(
                (data / "channel").stat().st_mode
            ),
            0o750,
        )

    def test_running_service_blocks_backup(self):

        self.rejected(
            "SERVICE_STOP_NOT_CONFIRMED",
            lambda: False,
        )

        self.assertFalse(
            self.final.exists()
        )

    def test_service_restarted_during_backup(self):

        stopped = mock.Mock(
            side_effect=[True, True, False]
        )

        self.rejected(
            "SERVICE_STOP_NOT_CONFIRMED",
            stopped,
        )

        self.assertEqual(
            list(self.root.iterdir()), []
        )

    def test_existing_backup_preserved(self):

        result = self.create()

        self.rejected(
            "BACKUP_ALREADY_EXISTS"
        )

        self.assertEqual(
            backup.verify_backup(
                self.final
            )["tree_sha256"],
            result["tree_sha256"],
        )

    def test_symlink_rejected(self):

        (self.source / "link").symlink_to(
            self.config
        )

        self.rejected(
            "UNSAFE_BACKUP_FILE"
        )

        self.assertFalse(
            self.final.exists()
        )

    def test_hardlink_rejected(self):

        os.link(
            self.config,
            self.source / "hardlink",
        )

        self.rejected(
            "BACKUP_HARDLINK_REJECTED"
        )

    def test_backup_size_limit(self):

        with mock.patch.object(
            backup, "MAX_BACKUP_BYTES", 1
        ):

            self.rejected(
                "BACKUP_SIZE_LIMIT"
            )

    def test_insufficient_space(self):

        with mock.patch.object(
            backup.shutil,
            "disk_usage",
            return_value=mock.Mock(free=0),
        ):

            self.rejected(
                "INSUFFICIENT_BACKUP_SPACE"
            )

        self.assertFalse(
            self.final.exists()
        )

    def test_corrupted_backup_detected(self):

        self.create()

        (
            self.final / "data/config"
        ).write_text("corrupted")

        with self.assertRaisesRegex(
            backup.BackupError,
            "^BACKUP_INTEGRITY_MISMATCH$",
        ):

            backup.verify_backup(
                self.final
            )

    def test_copy_failure_cleanup(self):

        with mock.patch.object(
            backup,
            "copy_file",
            side_effect=OSError(
                "simulated write failure"
            ),
        ):

            with self.assertRaises(OSError):
                self.create()

        self.assertEqual(
            list(self.root.iterdir()), []
        )

        self.assertTrue(
            self.config.exists()
        )

    def test_source_changed_during_backup(self):

        original = backup.copy_inventory

        def changed(*args):

            original(*args)

            self.config.write_text(
                "unexpected source modification"
            )

        with mock.patch.object(
            backup,
            "copy_inventory",
            side_effect=changed,
        ):

            self.rejected(
                "BACKUP_SOURCE_CHANGED"
            )

        self.assertFalse(
            self.final.exists()
        )


if __name__ == "__main__":
    unittest.main()
