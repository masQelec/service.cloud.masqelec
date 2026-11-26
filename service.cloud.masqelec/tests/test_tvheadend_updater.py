# -*- coding: utf-8 -*-

import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_updater as updater
from lib import tvheadend_transaction as tx
from lib import tvheadend_kodi as kodi


def make_addon(path, version):

    path.mkdir()
    (path / "bin").mkdir()

    (path / "addon.xml").write_text(
        f'<addon id="{tx.ADDON_ID}" '
        f'version="{version}"/>'
    )

    binary = path / "bin/tvheadend"

    binary.write_bytes(
        ("binary-" + version).encode()
    )

    binary.chmod(0o755)

    (path / "bin/tv_grab_file").write_text(
        "#!/bin/sh\n# masQelec\n"
    )


class FakeKodi:

    def __init__(self, active):

        self.active = active
        self.version = "21.2.7"
        self.enabled = True
        self.calls = []
        self.on_enable = lambda version: None

    def state(self):

        return kodi.AddonState(
            self.version, self.enabled
        )

    def set_enabled(self, enabled, version):

        if self.version != version:
            raise RuntimeError("version mismatch")

        self.calls.append(
            ("enabled", enabled, version)
        )

        self.enabled = enabled

        if enabled:
            self.on_enable(version)

        return self.state()

    def rescan_disabled(self, version):

        if self.enabled:
            raise RuntimeError("addon enabled")

        actual = tx.identity(
            self.active
        )["version"]

        if actual != version:
            raise RuntimeError("disk mismatch")

        self.version = actual

        self.calls.append(
            ("rescan", version)
        )

        return self.state()


class TvheadendUpdaterTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        addons = self.base / "addons"
        addons.mkdir()

        userdata = self.base / "addon_data"
        userdata.mkdir()

        self.active = addons / tx.ADDON_ID
        self.config = userdata / tx.ADDON_ID

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        self.candidate = self.root / "candidate"

        make_addon(self.active, "21.2.7")
        make_addon(self.candidate, "21.2.8")

        self.config.mkdir()

        self.config_file = self.config / "config"
        self.config_file.write_text("original")

        self.old = tx.identity(self.active)
        self.new = tx.identity(self.candidate)

        self.kodi = FakeKodi(self.active)

        self.events = []

        self.allowed = mock.Mock(return_value=True)
        self.recovery = mock.Mock(return_value=True)

        self.health = mock.Mock(
            return_value={"health": "PASS"}
        )

        self.stopped = lambda: not self.kodi.enabled

        self.worker = updater.TvheadendUpdater(
            self.active,
            self.config,
            self.root,
            self.kodi,
            self.stopped,
            self.health,
            self.allowed,
            self.recovery,
            notify=self.events.append,
            wait=lambda seconds: None,
        )

    def state(self):

        return self.worker._read()["state"]

    def fail_new_health(self):

        def verify(digest):

            if digest == self.new["binary_sha256"]:
                raise RuntimeError("new health failure")

            return {"health": "PASS"}

        self.health.side_effect = verify

        def modify(version):

            if version == "21.2.8":

                self.config_file.write_text(
                    "changed by new version"
                )

        self.kodi.on_enable = modify

    def assert_old_restored(self):

        self.assertEqual(
            tx.identity(self.active), self.old
        )

        self.assertEqual(
            self.kodi.state(),
            kodi.AddonState("21.2.7", True),
        )

        self.assertEqual(
            self.config_file.read_text(),
            "original",
        )

    def test_successful_update(self):

        self.assertEqual(
            self.worker.run(), "UPDATED"
        )

        self.assertEqual(
            self.state(), "COMMITTED"
        )

        self.assertEqual(
            tx.identity(self.active), self.new
        )

        self.assertEqual(
            tx.identity(self.candidate), self.old
        )

        self.assertEqual(
            self.kodi.state(),
            kodi.AddonState("21.2.8", True),
        )

        self.assertEqual(
            self.events,
            ["INSTALLING", "UPDATED"],
        )

    def test_activity_defers_update(self):

        self.allowed.return_value = False

        self.assertEqual(
            self.worker.run(),
            "DEFERRED_ACTIVITY",
        )

        self.assertFalse(
            self.worker.journal.exists()
        )

        self.assertEqual(self.kodi.calls, [])

    def test_activity_recheck_cancels(self):

        self.allowed.side_effect = [
            True, False
        ]

        self.assertEqual(
            self.worker.run(),
            "DEFERRED_ACTIVITY",
        )

        self.assertEqual(
            self.state(), "CANCELLED"
        )

        self.assertEqual(self.kodi.calls, [])

    def test_health_failure_restores_config(self):

        self.fail_new_health()

        self.assertEqual(
            self.worker.run(),
            "ROLLED_BACK",
        )

        self.assert_old_restored()

        self.assertEqual(
            self.state(), "ROLLED_BACK"
        )

        self.assertEqual(
            self.events,
            ["INSTALLING", "ROLLED_BACK"],
        )

    def test_backup_failure_recovers_old(self):

        with mock.patch.object(
            updater.backup,
            "create_backup",
            side_effect=OSError("backup failed"),
        ):

            self.assertEqual(
                self.worker.run(),
                "ROLLED_BACK",
            )

        self.assert_old_restored()

    def test_candidate_tree_mutation(self):

        original = self.worker._stop

        def changed(record):

            original(record)

            (
                self.candidate / "bin/tv_grab_file"
            ).write_text("unexpected")

        with mock.patch.object(
            self.worker,
            "_stop",
            side_effect=changed,
        ):

            self.assertEqual(
                self.worker.run(),
                "ROLLED_BACK",
            )

        self.assert_old_restored()

    def test_crash_after_swap(self):

        original = self.worker._phase

        def interrupted(record, state, **changes):

            if state == "SWAPPED":
                raise KeyboardInterrupt()

            return original(
                record, state, **changes
            )

        with mock.patch.object(
            self.worker,
            "_phase",
            side_effect=interrupted,
        ):

            with self.assertRaises(
                KeyboardInterrupt
            ):

                self.worker.run()

        self.assertEqual(
            self.state(), "BACKED_UP"
        )

        self.assertEqual(
            tx.identity(self.active), self.new
        )

        self.assertEqual(
            self.worker.recover(),
            "ROLLED_BACK",
        )

        self.assert_old_restored()

    def test_crash_after_new_service_started(self):

        def interrupted(version):

            if version == "21.2.8":

                self.config_file.write_text(
                    "modified before crash"
                )

                raise KeyboardInterrupt()

        self.kodi.on_enable = interrupted

        with self.assertRaises(
            KeyboardInterrupt
        ):

            self.worker.run()

        self.assertEqual(
            self.state(), "STARTING"
        )

        self.assertEqual(
            self.worker.recover(),
            "ROLLED_BACK",
        )

        self.assert_old_restored()

    def test_recovery_can_be_deferred(self):

        self.fail_new_health()
        self.recovery.return_value = False

        with self.assertRaisesRegex(
            updater.UpdateError,
            "^RECOVERY_REQUIRED$",
        ):

            self.worker.run()

        self.assertEqual(
            self.state(), "STARTING"
        )

        self.recovery.return_value = True

        self.assertEqual(
            self.worker.recover(),
            "ROLLED_BACK",
        )

        self.assert_old_restored()

    def test_crash_after_old_service_started(self):

        self.fail_new_health()

        previous = self.kodi.on_enable

        def interrupted(version):

            previous(version)

            if version == "21.2.7":

                self.config_file.write_text(
                    "old version already running"
                )

                raise KeyboardInterrupt()

        self.kodi.on_enable = interrupted

        with self.assertRaises(
            KeyboardInterrupt
        ):

            self.worker.run()

        self.assertEqual(
            self.state(), "ROLLBACK_STARTING"
        )

        self.assertEqual(
            self.worker.recover(),
            "ROLLED_BACK",
        )

        self.assertEqual(
            self.config_file.read_text(),
            "old version already running",
        )

    def test_committed_update_not_reverted(self):

        self.worker.run()

        self.assertEqual(
            self.worker.recover(),
            "COMMITTED",
        )

        self.assertEqual(
            tx.identity(self.active), self.new
        )

    def test_notification_failure_not_disruptive(self):

        self.worker.notify = mock.Mock(
            side_effect=RuntimeError(
                "notification error"
            ),
        )

        self.assertEqual(
            self.worker.run(), "UPDATED"
        )

        self.assertEqual(
            self.state(), "COMMITTED"
        )

    def test_pending_journal_blocks_new_update(self):

        self.worker.run()

        with self.assertRaisesRegex(
            updater.UpdateError,
            "^PENDING_TRANSACTION_EXISTS$",
        ):

            self.worker.run()

    def test_insufficient_recovery_space(self):

        with mock.patch.object(
            updater.shutil,
            "disk_usage",
            return_value=mock.Mock(free=0),
        ):

            with self.assertRaisesRegex(
                updater.UpdateError,
                "^INSUFFICIENT_RECOVERY_SPACE$",
            ):

                self.worker.run()

        self.assertEqual(self.kodi.calls, [])


    def interrupt_after_swap(self):

        original = self.worker._phase

        def interrupted(record, state, **changes):

            if state == "SWAPPED":
                raise KeyboardInterrupt()

            return original(
                record, state, **changes
            )

        with mock.patch.object(
            self.worker,
            "_phase",
            side_effect=interrupted,
        ):

            with self.assertRaises(KeyboardInterrupt):
                self.worker.run()

    def boot_recover(self, allowed=True):

        with mock.patch.object(
            self.worker,
            "kodi",
            None,
        ), mock.patch.object(
            self.worker,
            "verify_health",
            side_effect=AssertionError(
                "HTTP during early boot"
            ),
        ):

            return self.worker.recover_before_kodi(
                lambda: allowed
            )

    def test_boot_no_pending(self):

        self.assertEqual(
            self.boot_recover(),
            "NO_PENDING",
        )

        self.assertEqual(
            tx.identity(self.active), self.old
        )

    def test_boot_orphan_directory_journal(self):

        self.worker.directory.prepare()

        with self.assertRaisesRegex(
            updater.UpdateError,
            "^ORPHAN_DIRECTORY_JOURNAL$",
        ):

            self.boot_recover()

    def test_boot_prepared_cancelled(self):

        record = self.worker._preflight()
        self.worker._write(record)

        self.assertEqual(
            self.boot_recover(),
            "CANCELLED",
        )

        self.assertEqual(
            self.state(), "CANCELLED"
        )

        self.assertEqual(self.kodi.calls, [])

    def test_boot_quiescence_required(self):

        self.interrupt_after_swap()

        with self.assertRaisesRegex(
            updater.UpdateError,
            "^BOOT_QUIESCENCE_NOT_CONFIRMED$",
        ):

            self.boot_recover(False)

        self.assertEqual(
            tx.identity(self.active), self.new
        )

    def test_boot_recovery_after_swap(self):

        self.interrupt_after_swap()

        calls = list(self.kodi.calls)

        self.assertEqual(
            self.boot_recover(),
            "FILES_RECOVERED",
        )

        self.assertEqual(
            self.state(), "ROLLBACK_STARTING"
        )

        self.assertEqual(
            tx.identity(self.active), self.old
        )

        self.assertEqual(self.kodi.calls, calls)

        self.assertEqual(
            self.worker.recover(),
            "ROLLED_BACK",
        )

        self.assert_old_restored()

    def test_boot_recovery_after_new_start(self):

        def interrupted(version):

            if version == "21.2.8":

                self.config_file.write_text(
                    "new version modified config"
                )

                raise KeyboardInterrupt()

        self.kodi.on_enable = interrupted

        with self.assertRaises(KeyboardInterrupt):
            self.worker.run()

        self.assertEqual(
            self.state(), "STARTING"
        )

        self.kodi.enabled = False

        self.assertEqual(
            self.boot_recover(),
            "FILES_RECOVERED",
        )

        self.assertEqual(
            self.config_file.read_text(),
            "original",
        )

        self.assertEqual(
            tx.identity(self.active), self.old
        )

        self.assertEqual(
            self.worker.recover(),
            "ROLLED_BACK",
        )

        self.assert_old_restored()

    def test_boot_recovery_does_not_restore_twice(self):

        self.interrupt_after_swap()

        self.boot_recover()

        self.config_file.write_text(
            "old version modified config"
        )

        self.assertEqual(
            self.boot_recover(),
            "FILES_RECOVERED",
        )

        self.assertEqual(
            self.config_file.read_text(),
            "old version modified config",
        )

    def test_boot_committed_update_preserved(self):

        self.worker.run()

        self.assertEqual(
            self.boot_recover(),
            "COMMITTED",
        )

        self.assertEqual(
            tx.identity(self.active), self.new
        )


if __name__ == "__main__":
    unittest.main()
