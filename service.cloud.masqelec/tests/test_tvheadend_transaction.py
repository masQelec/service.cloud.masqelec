# -*- coding: utf-8 -*-

import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_transaction as tx


def stopped():
    return True


def make_addon(path, version):

    path.mkdir()

    (path / "bin").mkdir()

    (path / "addon.xml").write_text(
        f'<addon id="{tx.ADDON_ID}" '
        f'version="{version}"/>',
        encoding="utf-8",
    )

    binary = path / "bin" / "tvheadend"

    binary.write_bytes(
        ("binary-" + version).encode()
    )

    binary.chmod(0o755)


class TvheadendTransactionTests(
    unittest.TestCase
):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        addons = self.base / "addons"
        addons.mkdir()

        self.active = addons / tx.ADDON_ID

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        self.candidate = self.root / "candidate"

        make_addon(self.active, "21.2.7")
        make_addon(self.candidate, "21.2.8")

        self.transaction = (
            tx.DirectoryTransaction(
                self.active,
                self.root,
            )
        )

    def test_prepare_persistent_journal(self):

        record = self.transaction.prepare()

        self.assertEqual(
            record["state"], "PREPARED"
        )

        self.assertTrue(
            self.transaction.journal.is_file()
        )

        self.assertEqual(
            self.transaction.inspect(),
            {
                "state": "PREPARED",
                "orientation": "OLD_ACTIVE",
            },
        )

    def test_real_atomic_swap(self):

        self.transaction.prepare()

        result = self.transaction.swap(stopped)

        self.assertEqual(result, "SWAPPED")

        self.assertEqual(
            tx.identity(self.active)["version"],
            "21.2.8",
        )

        self.assertEqual(
            tx.identity(self.candidate)["version"],
            "21.2.7",
        )

    def test_real_atomic_rollback(self):

        self.transaction.prepare()
        self.transaction.swap(stopped)

        result = self.transaction.rollback(
            stopped
        )

        self.assertEqual(
            result, "ROLLED_BACK"
        )

        self.assertEqual(
            tx.identity(self.active)["version"],
            "21.2.7",
        )

    def test_service_running_blocks_swap(self):

        self.transaction.prepare()

        with self.assertRaisesRegex(
            tx.TransactionError,
            "^SERVICE_STOP_NOT_CONFIRMED$",
        ):

            self.transaction.swap(
                lambda: False
            )

        self.assertEqual(
            self.transaction.inspect()[
                "orientation"
            ],
            "OLD_ACTIVE",
        )

    def test_crash_after_exchange(self):

        self.transaction.prepare()

        original_write = (
            self.transaction._write
        )

        def interrupted(record):

            if record["state"] == "SWAPPED":
                raise OSError("simulated crash")

            original_write(record)

        with mock.patch.object(
            self.transaction,
            "_write",
            side_effect=interrupted,
        ):

            with self.assertRaises(OSError):

                self.transaction.swap(stopped)

        recovered = tx.DirectoryTransaction(
            self.active,
            self.root,
        )

        self.assertEqual(
            recovered.inspect(),
            {
                "state": "SWAPPING",
                "orientation": "NEW_ACTIVE",
            },
        )

        recovered.rollback(stopped)

        self.assertEqual(
            recovered.inspect(),
            {
                "state": "ROLLED_BACK",
                "orientation": "OLD_ACTIVE",
            },
        )

    def test_crash_before_exchange(self):

        self.transaction.prepare()

        with mock.patch.object(
            tx,
            "atomic_exchange",
            side_effect=OSError("simulated crash"),
        ):

            with self.assertRaises(OSError):

                self.transaction.swap(stopped)

        self.assertEqual(
            self.transaction.inspect(),
            {
                "state": "SWAPPING",
                "orientation": "OLD_ACTIVE",
            },
        )

        self.transaction.rollback(stopped)

        self.assertEqual(
            self.transaction.inspect()["state"],
            "ROLLED_BACK",
        )

    def test_no_downgrade(self):

        (self.candidate / "addon.xml").write_text(
            f'<addon id="{tx.ADDON_ID}" '
            'version="21.2.6"/>'
        )

        with self.assertRaisesRegex(
            tx.TransactionError,
            "^NOT_AN_UPGRADE$",
        ):

            self.transaction.prepare()

    def test_changed_candidate_detected(self):

        self.transaction.prepare()

        (self.candidate / "bin" / "tvheadend").write_bytes(
            b"unexpected modification"
        )

        with self.assertRaisesRegex(
            tx.TransactionError,
            "^TRANSACTION_IDENTITY_MISMATCH$",
        ):

            self.transaction.swap(stopped)

    def test_symlink_rejected(self):

        (self.candidate / "unsafe").symlink_to(
            self.active
        )

        with self.assertRaisesRegex(
            tx.TransactionError,
            "^UNSAFE_TREE_DIRECTORY$",
        ):

            self.transaction.prepare()

    def test_existing_journal_blocks_prepare(self):

        self.transaction.prepare()

        with self.assertRaisesRegex(
            tx.TransactionError,
            "^JOURNAL_ALREADY_EXISTS$",
        ):

            self.transaction.prepare()

    def test_corrupt_journal_blocks_recovery(self):

        self.transaction.prepare()

        self.transaction.journal.write_text(
            "invalid journal"
        )

        with self.assertRaisesRegex(
            tx.TransactionError,
            "^INVALID_JOURNAL$",
        ):

            self.transaction.rollback(stopped)

    def test_rollback_is_idempotent(self):

        self.transaction.prepare()
        self.transaction.swap(stopped)

        self.transaction.rollback(stopped)
        self.transaction.rollback(stopped)

        self.assertEqual(
            self.transaction.inspect(),
            {
                "state": "ROLLED_BACK",
                "orientation": "OLD_ACTIVE",
            },
        )


if __name__ == "__main__":
    unittest.main()
