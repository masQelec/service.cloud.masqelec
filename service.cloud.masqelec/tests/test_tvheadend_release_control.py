import tempfile
import unittest

from pathlib import Path
from types import SimpleNamespace

from lib import tvheadend_release_control as releases
from lib import tvheadend_transaction as tx

import test_tvheadend_updater as fixtures


class ReleaseControlTests(unittest.TestCase):

    def setUp(self):

        temporary = tempfile.TemporaryDirectory()

        self.addCleanup(temporary.cleanup)

        self.base = Path(
            temporary.name
        ).resolve()

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        self.control = releases.ReleaseControl(
            self.root
        )

        self.entry = SimpleNamespace(
            target="Amlogic-ng.arm",
            version="21.2.8",
            sha256="a" * 64,
        )

        self.candidate = self.root / "candidate"

        fixtures.make_addon(
            self.candidate,
            "21.2.8",
        )

        self.record = {
            "restore_required": True, "state": "ROLLED_BACK",
            "new": tx.identity(self.candidate),
        }

    def fail_release(self):

        self.control.record_candidate(
            self.entry,
            self.candidate,
        )

        self.control.before_archive(
            self.record
        )

    def test_failed_release_blocked(self):

        self.assertFalse(
            self.control.blocked(self.entry)
        )

        self.fail_release()

        self.assertTrue(
            self.control.blocked(self.entry)
        )

        self.assertTrue(
            releases.ReleaseControl(
                self.root
            ).blocked(self.entry)
        )

    def test_new_hash_allowed(self):

        self.fail_release()

        self.entry.sha256 = "b" * 64

        self.assertFalse(
            self.control.blocked(self.entry)
        )

    def test_failure_record_idempotent(self):

        self.fail_release()

        self.control.before_archive(
            self.record
        )

        self.assertEqual(
            len(list(
                self.control.failed.iterdir()
            )),
            1,
        )

    def test_cancelled_not_penalized(self):

        self.control.before_archive({
            "state": "CANCELLED"
        })

        self.assertFalse(
            self.control.blocked(self.entry)
        )

    def test_history_retention(self):

        history = self.control.history

        history.mkdir(mode=0o700)

        for state in (
            "committed",
            "rolled_back",
            "cancelled",
        ):

            for number in (1, 2, 3):

                path = history / (
                    state + "-"
                    + f"{number:032x}"
                )

                path.mkdir(mode=0o700)

                journal = path / "update.json"

                journal.write_bytes(
                    releases.encode({
                        "schema": 1,
                        "state": state.upper(),
                    })
                )

                journal.chmod(0o600)

        pending = history / (
            "committed-" + "f" * 32
        )

        pending.mkdir(mode=0o700)

        journal = pending / "update.json"

        journal.write_bytes(
            releases.encode({
                "schema": 1,
                "state": "STARTING",
            })
        )

        journal.chmod(0o600)

        self.assertEqual(
            self.control.prune_history(),
            6,
        )

        self.assertEqual(
            len(list(history.iterdir())),
            4,
        )

        self.assertTrue(pending.exists())
        self.assertTrue(self.root.exists())


if __name__ == "__main__":
    unittest.main()
