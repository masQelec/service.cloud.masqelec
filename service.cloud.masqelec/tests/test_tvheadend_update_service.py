# -*- coding: utf-8 -*-

import tempfile
import unittest

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from lib import tvheadend_boot as boot
from lib import tvheadend_lifecycle as lifecycle
from lib import tvheadend_transaction as tx
from lib import tvheadend_updater as updater
from lib import tvheadend_update_service as service

import test_tvheadend_updater as fixtures


class TvheadendUpdateServiceTests(
    unittest.TestCase
):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.parent = Path(
            self.tmp.name
        ).resolve()

        self.root = self.parent / "transaction"

        addons = self.parent / "addons"
        addons.mkdir()

        userdata = self.parent / "addon_data"
        userdata.mkdir()

        self.active = addons / tx.ADDON_ID
        self.config = userdata / tx.ADDON_ID

        fixtures.make_addon(
            self.active, "21.2.7"
        )

        self.config.mkdir()

        (
            self.config / "config"
        ).write_text("original")

        self.old = tx.identity(self.active)

        self.kodi = fixtures.FakeKodi(
            self.active
        )

        self.activity = mock.Mock(
            return_value=True
        )

        self.health = mock.Mock(
            return_value={"health": "PASS"}
        )

        self.protection = mock.Mock(
            return_value=True
        )

        self.detect = mock.Mock(
            return_value=object()
        )

        self.fetch = mock.Mock(
            return_value=object()
        )

        self.status = "UPDATE_AVAILABLE"

        self.events = []

        self.worker = updater.TvheadendUpdater(
            self.active,
            self.config,
            self.root,
            self.kodi,
            lambda: not self.kodi.enabled,
            self.health,
            self.activity,
            lambda: True,
            notify=self.events.append,
            wait=lambda seconds: None,
        )

        self.manager = lifecycle.Lifecycle(
            self.root
        )

    @contextmanager
    def stage(self, *args):

        decision = SimpleNamespace(
            status=self.status,
            package=object(),
        )

        zip_path = (
            Path("/synthetic/package.zip")
            if self.status == "UPDATE_AVAILABLE"
            else None
        )

        yield decision, zip_path

    def prepare(
        self,
        zip_path,
        entry,
        device,
        root,
        grabber,
    ):

        fixtures.make_addon(
            root / "candidate",
            "21.2.8",
        )

    def run_cycle(
        self,
        authorized=True,
        **overrides,
    ):

        options = {
            "authorized": authorized,
            "branch": "21",
            "base": (
                "https://raw.githubusercontent.com/"
                "masQelec/cloud.masqelec/21"
            ),
            "detect_device": self.detect,
            "fetch_manifest": self.fetch,
            "stage_package": self.stage,
            "prepare_candidate": self.prepare,
            "verify_protection": self.protection,
            "verify_recovery": lambda: True,
            "verify_policy": lambda: True,
        }

        options.update(overrides)

        return service.run_cycle(
            self.worker,
            **options,
        )

    def test_full_update_and_archive(self):

        self.assertEqual(
            self.run_cycle(),
            "UPDATED",
        )

        self.assertFalse(self.root.exists())

        self.assertEqual(
            tx.identity(self.active)["version"],
            "21.2.8",
        )

        history = list(
            self.manager.history.iterdir()
        )

        self.assertEqual(len(history), 1)

        self.assertTrue(
            history[0].name.startswith(
                "committed-"
            )
        )

        self.assertTrue(
            (
                history[0]
                / "config-backup/data/config"
            ).is_file()
        )

    def test_not_authorized(self):

        self.assertEqual(
            self.run_cycle(False),
            "NOT_AUTHORIZED",
        )

        self.fetch.assert_not_called()

        self.assertFalse(self.root.exists())

    def test_up_to_date(self):

        self.status = "UP_TO_DATE"

        self.assertEqual(
            self.run_cycle(),
            "UP_TO_DATE",
        )

        self.assertFalse(self.root.exists())
        self.assertEqual(self.kodi.calls, [])

    def test_local_newer_no_downgrade(self):

        self.status = "LOCAL_NEWER"

        self.assertEqual(
            self.run_cycle(),
            "LOCAL_NEWER",
        )

        self.assertEqual(self.kodi.calls, [])

    def test_activity_defers_before_network(self):

        self.activity.return_value = False

        self.assertEqual(
            self.run_cycle(),
            "DEFERRED_ACTIVITY",
        )

        self.fetch.assert_not_called()

    def test_boot_protection_required(self):

        self.protection.return_value = False

        with self.assertRaisesRegex(
            service.UpdateServiceError,
            "^BOOT_PROTECTION_NOT_READY$",
        ):

            self.run_cycle()

        self.assertEqual(self.kodi.calls, [])
        self.assertFalse(self.root.exists())

    def test_orphan_directory_journal_blocks(self):

        self.root.mkdir(mode=0o700)

        (
            self.root / "journal.json"
        ).write_text("unexpected")

        with self.assertRaisesRegex(
            service.UpdateServiceError,
            "^ORPHAN_DIRECTORY_JOURNAL$",
        ):

            self.run_cycle()

        self.fetch.assert_not_called()

    def test_interrupted_staging_archived(self):

        self.root.mkdir(mode=0o700)

        (
            self.root / "candidate"
        ).mkdir()

        (
            self.root / "candidate/partial"
        ).write_text("interrupted extraction")

        self.assertEqual(
            self.run_cycle(),
            "UPDATED",
        )

        history = list(
            self.manager.history.iterdir()
        )

        self.assertEqual(len(history), 2)

        self.assertTrue(
            any(
                path.name.startswith(
                    "unstarted-"
                )
                for path in history
            )
        )

    def test_pending_recovery_before_network(self):

        self.root.mkdir(mode=0o700)

        fixtures.make_addon(
            self.root / "candidate",
            "21.2.8",
        )

        def interrupt(version):

            if version == "21.2.8":

                (
                    self.config / "config"
                ).write_text("modified")

                raise KeyboardInterrupt()

        self.kodi.on_enable = interrupt

        with self.assertRaises(
            KeyboardInterrupt
        ):

            self.worker.run()

        self.assertEqual(
            self.run_cycle(),
            "ROLLED_BACK",
        )

        self.fetch.assert_not_called()
        self.detect.assert_not_called()

        self.assertEqual(
            tx.identity(self.active), self.old
        )

        self.assertEqual(
            (
                self.config / "config"
            ).read_text(),
            "original",
        )

    def test_failed_update_archived(self):

        self.health.side_effect = (
            lambda digest: {
                "health": (
                    "PASS"
                    if digest
                    == self.old["binary_sha256"]
                    else "FAILED"
                )
            }
        )

        self.assertEqual(
            self.run_cycle(),
            "ROLLED_BACK",
        )

        self.assertFalse(self.root.exists())

        self.assertEqual(
            tx.identity(self.active), self.old
        )

    def test_boot_and_runtime_share_lock(self):

        self.root.mkdir(mode=0o700)

        with self.manager.locked():

            with self.assertRaisesRegex(
                lifecycle.LifecycleError,
                "^LIFECYCLE_BUSY$",
            ):

                boot.recover_pending(
                    root=self.root,
                    active=self.active,
                    config=self.config,
                )

    def test_unexpected_staging_content_blocks(self):

        self.root.mkdir(mode=0o700)

        (
            self.root / "config-backup"
        ).mkdir()

        with self.assertRaisesRegex(
            lifecycle.LifecycleError,
            "^UNEXPECTED_UNSTARTED_CONTENT$",
        ):

            self.run_cycle()

        self.fetch.assert_not_called()

        self.assertTrue(
            (
                self.root / "config-backup"
            ).exists()
        )


    def test_unconfirmed_policy_blocks_download(self):

        self.assertEqual(
            self.run_cycle(
                verify_policy=lambda: False
            ),
            "DEFERRED_UPDATE_POLICY",
        )

        self.fetch.assert_not_called()

        self.assertFalse(self.root.exists())

        self.assertEqual(self.kodi.calls, [])

    def test_policy_lost_before_staging_blocks_install(self):

        guard = mock.Mock(
            side_effect=[True, False]
        )

        self.assertEqual(
            self.run_cycle(
                verify_policy=guard
            ),
            "DEFERRED_UPDATE_POLICY",
        )

        self.assertFalse(self.root.exists())

        self.assertEqual(self.kodi.calls, [])

        self.assertEqual(
            tx.identity(self.active),
            self.old,
        )


if __name__ == "__main__":
    unittest.main()
