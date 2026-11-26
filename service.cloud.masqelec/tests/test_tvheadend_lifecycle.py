# -*- coding: utf-8 -*-

import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_lifecycle as lifecycle
from lib import tvheadend_health as health
from lib import tvheadend_transaction as tx
from lib import tvheadend_updater as updater

import test_tvheadend_updater as fixtures


RUNNING = health.ServiceState(
    "loaded", "active", "running",
    1234, 0, "enabled",
)

INACTIVE = health.ServiceState(
    "loaded", "inactive", "dead",
    0, 0, "enabled",
)


class TvheadendLifecycleTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        addons = self.base / "addons"
        addons.mkdir()

        userdata = self.base / "addon_data"
        userdata.mkdir()

        self.active = addons / tx.ADDON_ID
        self.config = userdata / tx.ADDON_ID

        self.config.mkdir()

        (self.config / "config").write_text(
            "original"
        )

        fixtures.make_addon(
            self.active, "21.2.7"
        )

        fixtures.make_addon(
            self.root / "candidate",
            "21.2.8",
        )

        self.old = tx.identity(self.active)

        self.kodi = fixtures.FakeKodi(
            self.active
        )

        self.verify = mock.Mock(
            return_value={"health": "PASS"}
        )

        self.worker = updater.TvheadendUpdater(
            self.active,
            self.config,
            self.root,
            self.kodi,
            lambda: not self.kodi.enabled,
            self.verify,
            lambda: True,
            lambda: True,
            wait=lambda seconds: None,
        )

        self.lifecycle = lifecycle.Lifecycle(
            self.root
        )

        self.enable = mock.Mock()

    def archive(self):

        with self.lifecycle.locked():

            return (
                self.lifecycle.archive_terminal(
                    self.worker
                )
            )

    def repair(self, **changes):

        options = {
            "active": self.active,
            "read_state": lambda: INACTIVE,
            "scan_processes": lambda: (),
            "recovery_ready": lambda: True,
            "enable_service": self.enable,
        }

        options.update(changes)

        return lifecycle.repair_enabled_service(
            self.kodi,
            self.old,
            **options,
        )

    def test_archive_committed(self):

        self.assertEqual(
            self.worker.run(), "UPDATED"
        )

        target = self.archive()

        self.assertFalse(self.root.exists())

        self.assertTrue(
            (target / "update.json").is_file()
        )

        self.assertTrue(
            (target / "config-backup/data").is_dir()
        )

        self.assertTrue(
            self.lifecycle.lockfile.exists()
        )

    def test_archive_rolled_back(self):

        self.verify.side_effect = (
            lambda digest: (
                {"health": "PASS"}
                if digest == self.old["binary_sha256"]
                else {"health": "FAILED"}
            )
        )

        self.assertEqual(
            self.worker.run(),
            "ROLLED_BACK",
        )

        target = self.archive()

        self.assertTrue(
            target.name.startswith(
                "rolled_back-"
            )
        )

        self.assertEqual(
            tx.identity(self.active),
            self.old,
        )

    def test_archive_cancelled(self):

        self.worker.activity_allowed = mock.Mock(
            side_effect=[True, False]
        )

        self.assertEqual(
            self.worker.run(),
            "DEFERRED_ACTIVITY",
        )

        target = self.archive()

        self.assertTrue(
            target.name.startswith(
                "cancelled-"
            )
        )

    def test_pending_transaction_not_archived(self):

        record = self.worker._preflight()
        self.worker._write(record)

        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "^TRANSACTION_NOT_TERMINAL$",
        ):

            self.archive()

        self.assertTrue(
            self.root.exists()
        )

    def test_unhealthy_transaction_not_archived(self):

        self.worker.run()

        self.verify.return_value = {
            "health": "FAILED"
        }

        with self.assertRaisesRegex(
            updater.UpdateError,
            "^HEALTH_NOT_CONFIRMED$",
        ):

            self.archive()

        self.assertTrue(
            self.root.exists()
        )

    def test_stable_lock_excludes_second_worker(self):

        other = lifecycle.Lifecycle(
            self.root
        )

        with self.lifecycle.locked():

            with self.assertRaisesRegex(
                lifecycle.LifecycleError,
                "^LIFECYCLE_BUSY$",
            ):

                with other.locked():
                    pass

    def test_running_service_not_restarted(self):

        self.assertEqual(
            self.repair(
                read_state=lambda: RUNNING
            ),
            "ALREADY_RUNNING",
        )

        self.enable.assert_not_called()

    def test_missing_start_repaired(self):

        self.assertEqual(
            self.repair(),
            "START_REQUESTED",
        )

        self.enable.assert_called_once_with()

    def test_residual_process_blocks_repair(self):

        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "^REPAIR_RESIDUAL_PROCESS$",
        ):

            self.repair(
                scan_processes=lambda: (1234,)
            )

        self.enable.assert_not_called()

    def test_unready_protection_blocks_repair(self):

        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "^REPAIR_BOOT_PROTECTION_NOT_READY$",
        ):

            self.repair(
                recovery_ready=lambda: False
            )

        self.enable.assert_not_called()

    def test_unexpected_version_blocks_repair(self):

        self.kodi.version = "21.2.8"

        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "^REPAIR_KODI_STATE_MISMATCH$",
        ):

            self.repair()

        self.enable.assert_not_called()

    def test_coordinator_reconciliation_callback(self):

        callback = mock.Mock()

        self.worker.repair_enabled = callback

        self.worker._enable(self.old)

        callback.assert_called_once_with(
            self.old
        )

        self.assertEqual(
            self.kodi.calls, []
        )


if __name__ == "__main__":
    unittest.main()
