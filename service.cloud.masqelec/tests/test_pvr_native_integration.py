import ast
import threading
import unittest

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


ROOT = Path(__file__).resolve().parents[1]


def load_functions(relative, names, namespace):

    path = ROOT / relative
    tree = ast.parse(path.read_text())

    selected = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name in names
    ]

    assert {node.name for node in selected} == set(names)

    module = ast.Module(
        body=selected,
        type_ignores=[],
    )

    exec(
        compile(module, str(path), "exec"),
        namespace,
    )

    return namespace


class CoordinatorTests(unittest.TestCase):

    def setUp(self):

        self.calls = []

        def step(name, result):

            def run(*args, **kwargs):

                self.calls.append(name)

                return result

            return Mock(side_effect=run)

        self.pending = Mock(return_value=False)

        self.runtime = step(
            "tvheadend_update", "UP_TO_DATE"
        )

        self.settings = step(
            "xmltv_settings", "UNCHANGED"
        )

        self.credentials = step(
            "credentials", "UNCHANGED"
        )

        self.playlist = step(
            "playlist", {"status": "UNCHANGED"}
        )

        self.config = step(
            "tvheadend_config",
            {"status": "UNCHANGED"},
        )

        self.health = step("health", "PASS")

        self.ns = load_functions(
            "lib/update_pvr.py",
            {"update_pvr"},
            {
                "constants": SimpleNamespace(
                    CLOUD_BRANCH="21",
                    CLOUD_RAW_BASE="https://example.org",
                ),
                "log_utils": Mock(),
                "pending_transaction": self.pending,
                "runtime": SimpleNamespace(
                    run=self.runtime
                ),
                "pvr_epg_settings": SimpleNamespace(
                    ensure_settings=self.settings
                ),
                "pvr_credentials": SimpleNamespace(
                    ensure_credentials=self.credentials
                ),
                "pvr_playlist": SimpleNamespace(
                    update=self.playlist
                ),
                "pvr_config": SimpleNamespace(
                    ensure_config=self.config
                ),
                "check_stack": self.health,
                "UPDATE_SUCCESS": {
                    "UPDATED",
                    "UP_TO_DATE",
                    "NO_RELEASE",
                    "LOCAL_NEWER",
                },
                "RECOVERY_TERMINAL": {
                    "NO_PENDING",
                    "COMMITTED",
                    "ROLLED_BACK",
                    "CANCELLED",
                },
            },
        )

    def run_cycle(self):
        return self.ns["update_pvr"]()

    def test_no_release_keeps_native_maintenance(self):

        self.runtime.side_effect = None
        self.runtime.return_value = "NO_RELEASE"

        result = self.run_cycle()

        self.assertEqual(result["status"], "OK")

        self.playlist.assert_called_once()
        self.config.assert_called_once()
        self.health.assert_called_once()

    def test_normal_cycle(self):

        self.assertEqual(
            self.run_cycle()["status"], "OK"
        )

        self.assertEqual(
            self.calls,
            [
                "credentials",
                "playlist",
                "xmltv_settings",
                "tvheadend_update",
                "tvheadend_config",
                "health",
            ],
        )

    def test_recovery_has_priority(self):

        self.pending.side_effect = [True, False]

        self.runtime.side_effect = None
        self.runtime.return_value = "ROLLED_BACK"

        result = self.run_cycle()

        self.assertEqual(
            result["status"], "DEFERRED"
        )

        self.assertTrue(
            self.runtime.call_args.kwargs["recover_only"]
        )

        self.settings.assert_not_called()
        self.playlist.assert_not_called()
        self.config.assert_not_called()

    def test_recovery_failure_blocks_other_operations(self):

        self.pending.return_value = True

        self.runtime.side_effect = RuntimeError(
            "recovery failed"
        )

        self.assertEqual(
            self.run_cycle()["status"], "FAILED"
        )

        self.settings.assert_not_called()
        self.credentials.assert_not_called()
        self.playlist.assert_not_called()
        self.config.assert_not_called()

    def test_xmltv_failure_blocks_binary_update(self):

        self.settings.side_effect = RuntimeError(
            "settings failed"
        )

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")

        self.runtime.assert_not_called()
        self.playlist.assert_called_once()

    def test_playback_only_defers_binary_update(self):

        self.runtime.side_effect = None
        self.runtime.return_value = "DEFERRED_ACTIVITY"

        result = self.run_cycle()

        self.assertEqual(
            result["status"], "DEFERRED"
        )

        self.playlist.assert_called_once()
        self.config.assert_called_once()
        self.health.assert_called_once()

    def test_pending_after_update_blocks_mutations(self):

        self.pending.side_effect = [False, True]

        self.runtime.side_effect = RuntimeError(
            "update interrupted"
        )

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")

        self.credentials.assert_called_once()
        self.playlist.assert_called_once()
        self.settings.assert_called_once()
        self.runtime.assert_called_once()

        self.assertEqual(
            self.calls,
            ["credentials", "playlist", "xmltv_settings"],
        )

        self.assertIn(
            "pending_transaction", result["failures"]
        )

        self.config.assert_not_called()
        self.health.assert_not_called()

    def test_credentials_failure_blocks_playlist_and_update(self):

        self.credentials.side_effect = RuntimeError(
            "credentials unavailable"
        )

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")

        self.playlist.assert_not_called()
        self.runtime.assert_not_called()
        self.config.assert_called_once()
        self.health.assert_called_once()

    def test_health_failure_not_success(self):

        self.health.side_effect = RuntimeError(
            "PVR unavailable"
        )

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")

        self.assertIn("health", result["failures"])


    def test_playlist_download_failure_blocks_update(self):

        self.playlist.side_effect = RuntimeError(
            "download failed"
        )

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("playlist", result["failures"])

        self.runtime.assert_not_called()
        self.config.assert_called_once()
        self.health.assert_called_once()


    def test_playlist_invalid_status_blocks_update(self):

        self.playlist.side_effect = None
        self.playlist.return_value = {
            "status": "INVALID_PLAYLIST"
        }

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("playlist", result["failures"])

        self.runtime.assert_not_called()


    def test_credentials_invalid_status_blocks_update(self):

        self.credentials.side_effect = None
        self.credentials.return_value = "INVALID"

        result = self.run_cycle()

        self.assertEqual(result["status"], "FAILED")
        self.assertIn("credentials", result["failures"])

        self.playlist.assert_not_called()
        self.runtime.assert_not_called()


    def test_updated_playlist_precedes_binary_update(self):

        def update_playlist(*args, **kwargs):

            self.calls.append("playlist")

            return {"status": "UPDATED"}

        def update_tvheadend(*args, **kwargs):

            self.calls.append("tvheadend_update")

            self.assertEqual(
                self.calls,
                [
                    "credentials",
                    "playlist",
                    "xmltv_settings",
                    "tvheadend_update",
                ],
            )

            return "UPDATED"

        self.playlist.side_effect = update_playlist
        self.runtime.side_effect = update_tvheadend

        result = self.run_cycle()

        self.assertEqual(result["status"], "OK")

        self.assertEqual(
            result["steps"]["playlist"], "UPDATED"
        )

        self.assertEqual(
            result["steps"]["tvheadend_update"],
            "UPDATED",
        )


    def test_pending_convergence_defers_binary_update(self):

        self.runtime.side_effect = None

        self.runtime.return_value = (
            "DEFERRED_PLAYLIST_CONVERGENCE"
        )

        result = self.run_cycle()

        self.assertEqual(result["status"], "DEFERRED")

        self.assertEqual(
            result["deferred"], ["tvheadend_update"]
        )

        self.assertEqual(result["failures"], [])

        self.playlist.assert_called_once()
        self.config.assert_called_once()
        self.health.assert_called_once()


    def test_first_install_provisioned_credentials(self):

        def provision(*args, **kwargs):

            self.calls.append("credentials")

            return "PROVISIONED"

        self.credentials.side_effect = provision

        result = self.run_cycle()

        self.assertEqual(result["status"], "OK")

        self.assertEqual(
            result["steps"]["credentials"],
            "PROVISIONED",
        )

        self.assertEqual(
            self.calls,
            [
                "credentials",
                "playlist",
                "xmltv_settings",
                "tvheadend_update",
                "tvheadend_config",
                "health",
            ],
        )

        self.playlist.assert_called_once()
        self.runtime.assert_called_once()


class WorkerTests(unittest.TestCase):

    def setUp(self):

        self.clock = 100.0

        self.update = Mock(
            return_value={"status": "OK"}
        )

        self.success = Mock()
        self.failure = Mock()
        self.cooldown = Mock(return_value=False)

        self.settings = Mock(return_value=True)

        self.prefs = {
            "update_enabled": True,
            "update_period_hours": 12,
        }

        self.ns = load_functions(
            "service.py",
            {
                "_run_pvr_cycle",
                "_update_pvr_wrapper",
                "_periodic_pvr_worker",
            },
            {
                "time": SimpleNamespace(
                    monotonic=lambda: self.clock
                ),
                "_PVR_LOCK": threading.Lock(),
                "_last_pvrcheck_ts": None,
                "_last_pvr_attempt_ts": None,
                "_pvr_startup_finished_ts": None,
                "_PVR_RETRY_SECS": 300,
                "_task_is_in_cooldown": self.cooldown,
                "_task_mark_success": self.success,
                "_task_mark_failure": self.failure,
                "_get_bool_setting": self.settings,
                "_load_pvr_prefs": lambda: self.prefs,
                "_hours_to_secs": lambda h: h * 3600,
                "update_pvr": self.update,
                "log": Mock(),
            },
        )

    def startup(self):
        self.ns["_update_pvr_wrapper"]()

    def periodic(self):
        self.ns["_periodic_pvr_worker"]()

    def test_periodic_waits_for_startup(self):

        self.periodic()

        self.update.assert_not_called()

    def test_startup_and_periodic(self):

        self.startup()

        self.update.assert_called_once()

        self.periodic()

        self.update.assert_called_once()

        self.clock += 12 * 3600

        self.periodic()

        self.assertEqual(
            self.update.call_count, 2
        )

    def test_deferred_retry(self):

        self.update.return_value = {
            "status": "DEFERRED",
            "deferred": ["tvheadend_update"],
        }

        self.startup()

        self.success.assert_not_called()
        self.failure.assert_not_called()

        self.clock += 299

        self.periodic()

        self.update.assert_called_once()

        self.clock += 1

        self.periodic()

        self.assertEqual(
            self.update.call_count, 2
        )

    def test_failure_retry(self):

        self.update.return_value = {
            "status": "FAILED",
            "failures": ["playlist"],
        }

        self.startup()

        self.failure.assert_called_once()
        self.success.assert_not_called()

        self.assertIsNone(
            self.ns["_last_pvrcheck_ts"]
        )

        self.clock += 300

        self.periodic()

        self.assertEqual(
            self.update.call_count, 2
        )

    def test_cooldown_respected(self):

        self.cooldown.return_value = True

        self.startup()

        self.clock += 12 * 3600

        self.periodic()

        self.update.assert_not_called()

    def test_shared_lock(self):

        lock = self.ns["_PVR_LOCK"]

        lock.acquire()

        try:

            self.ns["_run_pvr_cycle"]()

            self.update.assert_not_called()

        finally:

            lock.release()

    def test_startup_disabled_periodic_respected(self):

        self.settings.return_value = False

        self.startup()

        self.periodic()

        self.update.assert_not_called()

        self.clock += 12 * 3600

        self.periodic()

        self.update.assert_called_once()

    def test_periodic_disabled(self):

        self.startup()

        self.prefs["update_enabled"] = False

        self.clock += 24 * 3600

        self.periodic()

        self.update.assert_called_once()

    def test_zero_period(self):

        self.startup()

        self.prefs["update_period_hours"] = 0

        self.clock += 24 * 3600

        self.periodic()

        self.update.assert_called_once()

    def test_retry_measured_after_completion(self):

        def slow_update():

            self.clock += 900

            return {
                "status": "DEFERRED",
            }

        self.update.side_effect = slow_update

        self.startup()

        self.periodic()

        self.update.assert_called_once()


if __name__ == "__main__":
    unittest.main()
