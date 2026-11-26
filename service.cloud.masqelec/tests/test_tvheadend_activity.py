# -*- coding: utf-8 -*-

import json
import unittest

from unittest import mock

from lib import tvheadend_activity as activity


def master_snapshot():

    return {
        "current_time": 1795700508,
        "next_activity": 1795734240,
        "subscription_count": 0,
        "connection_count": 1,
        "activities": {
            "dvr": 0,
            "ota_grabber": 0,
            "int_grabber": 1795734240,
            "mux_scheduler": 0,
        },
    }


def kodi_response(players):

    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": players,
    })


def idle_rpc(request):

    assert json.loads(request)["method"] == (
        "Player.GetActivePlayers"
    )

    return kodi_response([])


class TvheadendActivityTests(unittest.TestCase):

    def setUp(self):
        self.data = master_snapshot()

    def evaluate(self):
        return activity.evaluate_tvh_activity(
            self.data
        )

    def api(self, endpoint, timeout_s):

        self.assertEqual(
            endpoint, "status/activity"
        )

        self.assertEqual(
            timeout_s,
            activity.API_TIMEOUT_SECONDS,
        )

        return True, 200, self.data, ""

    def test_master_idle_snapshot(self):

        result = self.evaluate()

        self.assertEqual(
            result.status, activity.IDLE
        )

        self.assertTrue(result.allowed)

    def test_idle_connections_allowed(self):

        self.data["connection_count"] = 10

        self.assertTrue(
            self.evaluate().allowed
        )

    def test_active_subscription_blocks(self):

        self.data["subscription_count"] = 1

        self.assertEqual(
            self.evaluate().status,
            activity.DEFERRED_TVH_SUBSCRIPTIONS,
        )

    def test_recording_in_progress(self):

        self.data["activities"]["dvr"] = (
            self.data["current_time"] - 60
        )

        self.assertEqual(
            self.evaluate().status,
            activity.DEFERRED_RECORDING,
        )

    def test_recording_starting_now(self):

        self.data["activities"]["dvr"] = (
            self.data["current_time"]
        )

        self.assertEqual(
            self.evaluate().status,
            activity.DEFERRED_RECORDING,
        )

    def test_upcoming_recording_guard(self):

        for remaining in (1, 60, 899, 900):

            with self.subTest(remaining=remaining):

                self.data["activities"]["dvr"] = (
                    self.data["current_time"]
                    + remaining
                )

                self.assertEqual(
                    self.evaluate().status,
                    activity.DEFERRED_UPCOMING_RECORDING,
                )

    def test_recording_outside_guard(self):

        self.data["activities"]["dvr"] = (
            self.data["current_time"] + 901
        )

        self.assertTrue(
            self.evaluate().allowed
        )

    def test_background_activity_guard(self):

        for key in activity.BACKGROUND_KEYS:

            for remaining in (-1, 0, 120):

                with self.subTest(
                    key=key,
                    remaining=remaining,
                ):

                    self.data = master_snapshot()

                    self.data["activities"][key] = (
                        self.data["current_time"]
                        + remaining
                    )

                    self.assertEqual(
                        self.evaluate().status,
                        activity.DEFERRED_BACKGROUND_ACTIVITY,
                    )

    def test_background_outside_guard(self):

        for key in activity.BACKGROUND_KEYS:

            self.data["activities"][key] = (
                self.data["current_time"] + 121
            )

        self.assertTrue(
            self.evaluate().allowed
        )

    def test_missing_required_fields(self):

        for key in (
            "current_time",
            "subscription_count",
            "connection_count",
            "activities",
        ):

            with self.subTest(key=key):

                self.data = master_snapshot()
                del self.data[key]

                self.assertEqual(
                    self.evaluate().status,
                    activity.DEFERRED_ACTIVITY_UNKNOWN,
                )

    def test_invalid_numeric_fields(self):

        for value in (
            None, True, -1, "0", 0.0
        ):

            with self.subTest(value=value):

                self.data = master_snapshot()

                self.data["subscription_count"] = (
                    value
                )

                self.assertEqual(
                    self.evaluate().status,
                    activity.DEFERRED_ACTIVITY_UNKNOWN,
                )

    def test_invalid_activity_schedule(self):

        for value in (None, False, -1, "0"):

            with self.subTest(value=value):

                self.data["activities"]["dvr"] = (
                    value
                )

                self.assertFalse(
                    self.evaluate().allowed
                )

    def test_kodi_playback_blocks_before_http(self):

        rpc = lambda request: kodi_response([
            {"playerid": 1, "type": "video"}
        ])

        api = mock.Mock()

        result = activity.check_activity(
            rpc, api
        )

        self.assertEqual(
            result.status,
            activity.DEFERRED_KODI_PLAYBACK,
        )

        api.assert_not_called()

    def test_invalid_kodi_response_blocks(self):

        for raw in (
            "",
            "invalid",
            "{}",
            '{"jsonrpc":"2.0","id":1,"result":{}}',
            '{"jsonrpc":"2.0","id":true,"result":[]}',
            '{"jsonrpc":"2.0","id":1,"error":{}}',
        ):

            with self.subTest(raw=raw):

                api = mock.Mock()

                result = activity.check_activity(
                    lambda request: raw,
                    api,
                )

                self.assertEqual(
                    result.status,
                    activity.DEFERRED_ACTIVITY_UNKNOWN,
                )

                api.assert_not_called()

    def test_kodi_rpc_exception_blocks(self):

        rpc = mock.Mock(
            side_effect=RuntimeError("RPC unavailable")
        )

        api = mock.Mock()

        result = activity.check_activity(
            rpc, api
        )

        self.assertFalse(result.allowed)
        api.assert_not_called()

    def test_http_failure_blocks(self):

        for response in (
            (False, 401, None, ""),
            (False, 403, None, ""),
            (False, 0, None, ""),
            (True, 500, self.data, ""),
            (True, 200, None, ""),
        ):

            api = mock.Mock(
                return_value=response
            )

            self.assertEqual(
                activity.check_activity(
                    idle_rpc, api
                ).status,
                activity.DEFERRED_ACTIVITY_UNKNOWN,
            )

    def test_http_exception_blocks(self):

        api = mock.Mock(
            side_effect=TimeoutError()
        )

        self.assertEqual(
            activity.check_activity(
                idle_rpc, api
            ).status,
            activity.DEFERRED_ACTIVITY_UNKNOWN,
        )

    def test_playback_started_during_http_query(self):

        rpc = mock.Mock(side_effect=[
            kodi_response([]),
            kodi_response([
                {"playerid": 1, "type": "video"}
            ]),
        ])

        result = activity.check_activity(
            rpc, self.api
        )

        self.assertEqual(
            result.status,
            activity.DEFERRED_KODI_PLAYBACK,
        )

        self.assertEqual(rpc.call_count, 2)

    def test_complete_idle_check(self):

        rpc = mock.Mock(
            return_value=kodi_response([])
        )

        api = mock.Mock(
            side_effect=self.api
        )

        result = activity.check_activity(
            rpc, api
        )

        self.assertTrue(result.allowed)
        self.assertEqual(rpc.call_count, 2)
        self.assertEqual(api.call_count, 1)


if __name__ == "__main__":
    unittest.main()
