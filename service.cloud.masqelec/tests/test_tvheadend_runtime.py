import unittest

from types import SimpleNamespace
from unittest import mock

from lib import tvheadend_runtime as runtime
from lib import tvheadend_health as health


class RuntimeAdapterTests(unittest.TestCase):

    def test_unauthorized_no_runtime_changes(self):

        with mock.patch.object(
            runtime.install,
            "is_coreelec_root",
        ) as platform:

            self.assertEqual(
                runtime.run(
                    branch="21",
                    base="",
                    authorized=False,
                ),
                "NOT_AUTHORIZED",
            )

            platform.assert_not_called()

    def test_notification_without_interaction(self):

        xbmc = mock.Mock()
        gui = mock.Mock()

        notifier = runtime.make_notifier(
            xbmc, gui
        )

        notifier("DEFERRED_ACTIVITY")

        gui.Dialog.assert_not_called()

        notifier("UPDATED")

        gui.Dialog.return_value.notification \
            .assert_called_once()

    def test_offline_service_recovery_allowed(self):

        stopped = health.ServiceState(
            "loaded",
            "inactive",
            "dead",
            0,
            0,
            "disabled",
        )

        with mock.patch.object(
            runtime.activity,
            "check_kodi_activity",
            return_value=SimpleNamespace(
                allowed=True
            ),
        ), mock.patch.object(
            runtime.health,
            "read_service",
            return_value=stopped,
        ), mock.patch.object(
            runtime.health,
            "find_tvheadend_processes",
            return_value=(),
        ):

            self.assertTrue(
                runtime.recovery_allowed(
                    mock.Mock(),
                    mock.Mock(),
                )
            )


if __name__ == "__main__":
    unittest.main()
