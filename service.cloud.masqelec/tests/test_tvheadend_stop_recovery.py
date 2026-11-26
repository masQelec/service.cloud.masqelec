import tempfile
import unittest

from pathlib import Path
from unittest.mock import Mock, patch

from lib import tvheadend_boot as boot
from lib import tvheadend_boot_install as install
from lib import tvheadend_health as health
from lib import tvheadend_lifecycle as lifecycle
from lib import tvheadend_release_control as releases
from lib import tvheadend_update_service as service
from lib import tvheadend_updater as updater


RUNNING = health.ServiceState(
    "loaded", "active", "running", 3759, 0, "enabled"
)

STOPPED_ENABLED = health.ServiceState(
    "loaded", "inactive", "dead", 0, 0, "enabled"
)

REMOVED = health.ServiceState(
    "not-found", "inactive", "dead", 0, 0, ""
)

FAILED_REMOVED = health.ServiceState(
    "not-found", "failed", "failed", 0, 0, ""
)

FAILED_ENABLED = health.ServiceState(
    "loaded", "failed", "failed", 0, 0, "enabled"
)


class StopRecoveryTests(unittest.TestCase):

    def test_failed_service_is_not_cleanly_stopped(self):

        self.assertTrue(FAILED_REMOVED.failed_stop)

        self.assertFalse(FAILED_REMOVED.stopped)

        self.assertFalse(
            health.is_stopped(
                read_state=lambda: FAILED_REMOVED,
                scan_processes=lambda: (),
            )
        )

    def test_failed_service_with_pid_rejected(self):

        state = health.ServiceState(
            "loaded", "failed", "failed",
            3759, 0, "enabled",
        )

        self.assertFalse(state.failed_stop)

    def test_real_missing_unit_failed_output(self):

        raw = (
            "LoadState=not-found\n"
            "ActiveState=failed\n"
            "SubState=failed\n"
            "MainPID=0\n"
            "ControlPID=0\n"
            "UnitFileState=\n"
        )

        result = Mock(
            returncode=1,
            stdout=raw,
        )

        with patch.object(
            health.subprocess,
            "run",
            return_value=result,
        ):

            self.assertEqual(
                health.read_service(),
                FAILED_REMOVED,
            )

    def test_stop_timeout_override(self):

        ctl = Mock(
            return_value="TimeoutStopUSec=1min\n"
        )

        self.assertTrue(
            install.verify_stop_timeout(ctl)
        )

    def test_original_two_second_timeout_rejected(self):

        ctl = Mock(
            return_value="TimeoutStopUSec=2s\n"
        )

        with self.assertRaises(
            install.BootInstallError
        ):

            install.verify_stop_timeout(ctl)

    def test_native_stop_checks_result_before_disable(self):

        ctl = Mock(side_effect=[
            "TimeoutStopUSec=1min\n",
            "",
            "",
            (
                "Result=success\n"
                "ExecMainCode=1\n"
                "ExecMainStatus=0\n"
            ),
            "",
        ])

        read = Mock(side_effect=[
            RUNNING,
            RUNNING,
            STOPPED_ENABLED,
            STOPPED_ENABLED,
        ])

        result = lifecycle.stop_for_update(
            ctl=ctl,
            read_state=read,
            scan_processes=lambda: (),
        )

        self.assertEqual(
            result, "STOPPED_CLEANLY"
        )

        ctl.assert_any_call(
            "stop", boot.TVH_UNIT
        )

    def test_native_stop_sigkill_rejected(self):

        ctl = Mock(side_effect=[
            "TimeoutStopUSec=1min\n",
            "",
            "",
            (
                "Result=timeout\n"
                "ExecMainCode=2\n"
                "ExecMainStatus=9\n"
            ),
        ])

        read = Mock(side_effect=[
            RUNNING,
            RUNNING,
            STOPPED_ENABLED,
        ])

        with self.assertRaises(
            lifecycle.LifecycleError
        ):

            lifecycle.stop_for_update(
                ctl=ctl,
                read_state=read,
                scan_processes=lambda: (),
            )

    def test_normalize_removed_failed_unit(self):

        ctl = Mock(return_value="")

        read = Mock(side_effect=[
            FAILED_REMOVED,
            REMOVED,
            REMOVED,
        ])

        result = lifecycle.normalize_failed_stop(
            FAILED_REMOVED,
            False,
            ctl=ctl,
            read_state=read,
            scan_processes=lambda: (),
        )

        self.assertEqual(result, REMOVED)

        ctl.assert_any_call(
            "reset-failed", boot.TVH_UNIT
        )

    def test_normalize_enabled_failed_unit(self):

        ctl = Mock(return_value="")

        read = Mock(side_effect=[
            FAILED_ENABLED,
            STOPPED_ENABLED,
            STOPPED_ENABLED,
        ])

        result = lifecycle.normalize_failed_stop(
            FAILED_ENABLED,
            True,
            ctl=ctl,
            read_state=read,
            scan_processes=lambda: (),
        )

        self.assertEqual(
            result, STOPPED_ENABLED
        )

    def test_remaining_process_blocks_reset(self):

        ctl = Mock()

        with self.assertRaises(
            lifecycle.LifecycleError
        ):

            lifecycle.normalize_failed_stop(
                FAILED_REMOVED,
                False,
                ctl=ctl,
                read_state=lambda: FAILED_REMOVED,
                scan_processes=lambda: (3759,),
            )

        ctl.assert_not_called()

    def test_pending_job_blocks_reset(self):

        ctl = Mock(
            return_value=(
                "21 service.tvheadend43.service "
                "start waiting\n"
            )
        )

        with self.assertRaises(
            lifecycle.LifecycleError
        ):

            lifecycle.normalize_failed_stop(
                FAILED_REMOVED,
                False,
                ctl=ctl,
                read_state=lambda: FAILED_REMOVED,
                scan_processes=lambda: (),
            )

        self.assertFalse(
            any(
                call.args[0] == "reset-failed"
                for call in ctl.call_args_list
            )
        )

    def test_unclean_stop_never_disables_addon(self):

        worker = updater.TvheadendUpdater.__new__(
            updater.TvheadendUpdater
        )

        worker.kodi = Mock()

        worker.kodi.state.return_value = Mock(
            enabled=True,
            version="21.2.7",
        )

        worker.stop_native = Mock(
            side_effect=lifecycle.LifecycleError(
                "NATIVE_STOP_UNCLEAN"
            )
        )

        record = {
            "old": {"version": "21.2.7"},
            "new": {"version": "21.2.8"},
        }

        with self.assertRaises(
            lifecycle.LifecycleError
        ):

            worker._stop(
                record,
                for_update=True,
            )

        worker.kodi.set_enabled.assert_not_called()

    def test_candidate_never_started_not_blacklisted(self):

        with tempfile.TemporaryDirectory() as temp:

            root = Path(temp) / "update"

            control = releases.ReleaseControl(root)

            control.before_archive({
                "state": "ROLLED_BACK",
                "restore_required": False,
            })

            self.assertFalse(
                control.failed.exists()
            )

    def test_recovery_does_not_require_loaded_tvh_unit(self):

        with tempfile.TemporaryDirectory() as temp:

            root = Path(temp) / "update"

            root.mkdir(mode=0o700)

            journal = root / "update.json"

            journal.touch()

            worker = Mock()

            worker.root = root
            worker.journal = journal

            worker.directory.journal = (
                root / "journal.json"
            )

            worker._read.return_value = {
                "state": "DISABLING"
            }

            worker.recover.return_value = (
                "ROLLED_BACK"
            )

            manager = Mock()

            from contextlib import nullcontext

            manager.locked.return_value = (
                nullcontext()
            )

            new_install_protection = Mock(
                side_effect=AssertionError(
                    "NEW_INSTALL_CHECK_DURING_RECOVERY"
                )
            )

            fetch = Mock(
                side_effect=AssertionError(
                    "NETWORK_DURING_RECOVERY"
                )
            )

            with patch.object(
                service.lifecycle,
                "Lifecycle",
                return_value=manager,
            ):

                result = service.run_cycle(
                    worker,
                    branch="21",
                    base="unused",
                    authorized=True,
                    verify_protection=new_install_protection,
                    verify_recovery=lambda: True,
                    fetch_manifest=fetch,
                )

            self.assertEqual(
                result, "ROLLED_BACK"
            )

            worker.recover.assert_called_once()

            new_install_protection.assert_not_called()
            fetch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
