import calendar
import unittest

from unittest.mock import Mock, patch

from lib import tvheadend_activity as activity


class LegacyActivityTests(unittest.TestCase):

    def setUp(self):

        self.now = calendar.timegm(
            (2026, 11, 26, 23, 30, 0)
        )

        self.rows = {
            "status/subscriptions": [],
            "status/inputs": [],
            "dvr/entry/grid_upcoming": [],
            "mpegts/mux_sched/grid": [],
        }

        self.epg = {
            "cron": "4 */12 * * *",
            "ota_cron": (
                "# Default config\n"
                "4 2 * * *\n"
                "4 14 * * *"
            ),
            "ota_timeout": 600,
        }

        self.clock = patch.object(
            activity.time,
            "localtime",
            side_effect=activity.time.gmtime,
        )

        self.clock.start()
        self.addCleanup(self.clock.stop)

        self.calls = []

    def api(self, endpoint, **kwargs):

        self.calls.append(endpoint)

        if endpoint == "status/activity":
            return False, 404, None, ""

        if endpoint == "epggrab/config/load":

            return True, 200, {
                "entries": [{
                    "params": [
                        {"id": key, "value": value}
                        for key, value in self.epg.items()
                    ]
                }]
            }, ""

        rows = self.rows[endpoint]

        return True, 200, {
            "entries": rows,
            "total": len(rows),
        }, ""

    def evaluate(self):

        return activity.check_legacy_activity(
            self.api,
            now=self.now,
        ).status

    def recording(self, remaining):

        self.rows["dvr/entry/grid_upcoming"] = [{
            "enabled": True,
            "sched_status": "scheduled",
            "start_real": self.now + remaining,
            "stop_real": self.now + remaining + 3600,
        }]

    def test_idle(self):

        self.assertEqual(
            self.evaluate(), activity.IDLE
        )

    def test_active_subscription(self):

        self.rows["status/subscriptions"] = [{}]

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_TVH_SUBSCRIPTIONS,
        )

    def test_active_input(self):

        self.rows["status/inputs"] = [{}]

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_BACKGROUND_ACTIVITY,
        )

    def test_recording_in_progress(self):

        self.recording(-60)

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_RECORDING,
        )

    def test_upcoming_recording(self):

        self.recording(900)

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_UPCOMING_RECORDING,
        )

    def test_recording_outside_guard(self):

        self.recording(901)

        self.assertEqual(
            self.evaluate(), activity.IDLE
        )

    def test_recording_status_blocks(self):

        self.recording(3600)

        self.rows["dvr/entry/grid_upcoming"][0][
            "sched_status"
        ] = "recording"

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_RECORDING,
        )

    def test_missing_real_start(self):

        self.recording(3600)

        del self.rows[
            "dvr/entry/grid_upcoming"
        ][0]["start_real"]

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_ACTIVITY_UNKNOWN,
        )

    def test_epg_about_to_start(self):

        self.now = calendar.timegm(
            (2026, 11, 27, 0, 2, 0)
        )

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_BACKGROUND_ACTIVITY,
        )

    def test_epg_recently_started(self):

        self.now = calendar.timegm(
            (2026, 11, 27, 0, 10, 0)
        )

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_BACKGROUND_ACTIVITY,
        )

    def test_ota_about_to_start(self):

        self.now = calendar.timegm(
            (2026, 11, 27, 2, 3, 0)
        )

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_BACKGROUND_ACTIVITY,
        )

    def test_unsupported_cron(self):

        self.epg["cron"] = "0 4 * * 1"

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_ACTIVITY_UNKNOWN,
        )

    def test_mux_schedule_unknown(self):

        self.rows["mpegts/mux_sched/grid"] = [{}]

        self.assertEqual(
            self.evaluate(),
            activity.DEFERRED_ACTIVITY_UNKNOWN,
        )

    def test_incomplete_grid(self):

        result = activity.check_legacy_activity(
            lambda *args, **kwargs: (
                True, 200,
                {"total": 3, "entries": []},
                "",
            ),
            now=self.now,
        )

        self.assertEqual(
            result.status,
            activity.DEFERRED_ACTIVITY_UNKNOWN,
        )

    def test_legacy_selected_on_404(self):

        rpc = Mock(return_value=(
            '{"jsonrpc":"2.0","id":1,"result":[]}'
        ))

        with patch.object(
            activity.time,
            "time",
            return_value=self.now,
        ):

            result = activity.check_activity(
                rpc, self.api
            )

        self.assertTrue(result.allowed)

        self.assertEqual(rpc.call_count, 2)

        self.assertEqual(
            self.calls[0], "status/activity"
        )

    def test_no_fallback_on_authentication_failure(self):

        api = Mock(return_value=(
            False, 403, None, ""
        ))

        rpc = Mock(return_value=(
            '{"jsonrpc":"2.0","id":1,"result":[]}'
        ))

        result = activity.check_activity(
            rpc, api
        )

        self.assertFalse(result.allowed)
        api.assert_called_once()

    def test_subscription_started_during_check(self):

        queries = 0

        def api(endpoint, **kwargs):

            nonlocal queries

            if endpoint == "status/subscriptions":

                queries += 1

                if queries == 2:
                    self.rows[endpoint] = [{}]

            return self.api(endpoint, **kwargs)

        result = activity.check_legacy_activity(
            api, now=self.now
        )

        self.assertEqual(
            result.status,
            activity.DEFERRED_TVH_SUBSCRIPTIONS,
        )


if __name__ == "__main__":
    unittest.main()
