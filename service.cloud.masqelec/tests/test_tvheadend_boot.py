# -*- coding: utf-8 -*-

import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_boot as boot


IDLE = {
    "LoadState": "loaded",
    "ActiveState": "inactive",
    "SubState": "dead",
    "MainPID": "0",
    "ControlPID": "0",
}

RUNNING = {
    **IDLE,
    "ActiveState": "active",
    "SubState": "running",
    "MainPID": "1234",
}

MISSING = {
    **IDLE,
    "LoadState": "not-found",
}


class TvheadendBootTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        self.root = self.base / "transaction"

    def quiescent(self, kodi=IDLE, tvh=IDLE):

        states = {
            boot.KODI_UNIT: kodi,
            boot.TVH_UNIT: tvh,
        }

        return boot.boot_quiescent(
            lambda unit: states[unit],
            lambda: (),
        )

    def test_services_quiescent(self):

        self.assertTrue(
            self.quiescent()
        )

    def test_kodi_running_blocks_recovery(self):

        self.assertFalse(
            self.quiescent(kodi=RUNNING)
        )

    def test_tvh_running_blocks_recovery(self):

        self.assertFalse(
            self.quiescent(tvh=RUNNING)
        )

    def test_tvh_unit_missing_is_allowed(self):

        self.assertTrue(
            self.quiescent(tvh=MISSING)
        )

    def test_kodi_unit_missing_is_rejected(self):

        self.assertFalse(
            self.quiescent(kodi=MISSING)
        )

    def test_control_process_blocks_recovery(self):

        state = {
            **IDLE,
            "ControlPID": "4321",
        }

        self.assertFalse(
            self.quiescent(tvh=state)
        )

    def test_residual_tvh_process_blocks(self):

        self.assertFalse(
            boot.boot_quiescent(
                lambda unit: IDLE,
                lambda: (1234,),
            )
        )

    def test_state_changed_during_probe(self):

        read = mock.Mock(
            side_effect=[
                IDLE, IDLE,
                RUNNING, IDLE,
            ],
        )

        self.assertFalse(
            boot.boot_quiescent(
                read,
                lambda: (),
            )
        )

    def test_systemd_failure_blocks(self):

        self.assertFalse(
            boot.boot_quiescent(
                mock.Mock(
                    side_effect=OSError(
                        "systemd unavailable"
                    ),
                ),
                lambda: (),
            )
        )

    def test_parse_unit_state(self):

        raw = "\n".join(
            f"{key}={value}"
            for key, value in IDLE.items()
        )

        self.assertEqual(
            boot.parse_unit_state(raw),
            IDLE,
        )

        with self.assertRaises(
            boot.BootRecoveryError
        ):

            boot.parse_unit_state(
                raw + "\nMainPID=1"
            )

    def test_no_transaction_root(self):

        self.assertEqual(
            boot.recover_pending(
                root=self.root
            ),
            "NO_PENDING",
        )

        self.assertFalse(
            self.root.exists()
        )

    def test_symlink_transaction_root(self):

        self.root.symlink_to(self.base)

        with self.assertRaisesRegex(
            boot.BootRecoveryError,
            "^UNSAFE_BOOT_TRANSACTION_ROOT$",
        ):

            boot.recover_pending(
                root=self.root
            )

    def test_empty_private_transaction_root(self):

        self.root.mkdir(mode=0o700)

        self.assertEqual(
            boot.recover_pending(
                root=self.root
            ),
            "NO_PENDING",
        )

    def test_recovery_result_propagated(self):

        self.root.mkdir(mode=0o700)

        callback = lambda: True

        with mock.patch.object(
            boot.updater,
            "TvheadendUpdater",
        ) as constructor:

            worker = constructor.return_value

            worker.recover_before_kodi.return_value = (
                "FILES_RECOVERED"
            )

            result = boot.recover_pending(
                root=self.root,
                assert_quiescent=callback,
            )

            worker.recover_before_kodi.assert_called_once_with(
                callback
            )

            self.assertEqual(
                result, "FILES_RECOVERED"
            )

    def test_unit_dependencies(self):

        self.assertIn(
            "RemainAfterExit=yes",
            boot.UNIT,
        )

        self.assertIn(
            "Before=kodi.service service.tvheadend43.service",
            boot.UNIT,
        )

        self.assertIn(
            "Wants=" + boot.UNIT_NAME,
            boot.KODI_DROPIN,
        )

        self.assertNotIn(
            "Requires=",
            boot.KODI_DROPIN,
        )

        self.assertIn(
            "Requires=" + boot.UNIT_NAME,
            boot.TVH_DROPIN,
        )


if __name__ == "__main__":
    unittest.main()
