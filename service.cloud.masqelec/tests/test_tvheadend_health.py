# -*- coding: utf-8 -*-

import hashlib
import os
import sys
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_health as health


RUNNING = health.ServiceState(
    "loaded", "active", "running",
    1234, 0, "enabled",
)

STOPPED = health.ServiceState(
    "loaded", "inactive", "dead",
    0, 0, "disabled",
)

REMOVED = health.ServiceState(
    "not-found", "inactive", "dead",
    0, 0, "",
)

SHA256 = "a" * 64

TOKEN = (
    1234, 100, 1, 10, 20, 30, 40
)


class TvheadendHealthTests(unittest.TestCase):

    def verify(self, **overrides):

        kwargs = {
            "read_state": lambda: RUNNING,
            "prove": lambda pid, path: (
                TOKEN, SHA256
            ),
            "token": lambda pid, path: TOKEN,
            "htsp_probe": lambda: True,
        }

        api = overrides.pop(
            "api_get",
            lambda *a, **k: (
                True,
                200,
                {"sw_version": "4.3-test"},
                "",
            ),
        )

        kwargs.update(overrides)

        return health.verify_running(
            SHA256,
            api,
            **kwargs,
        )

    def rejected(self, code, **kwargs):

        with self.assertRaisesRegex(
            health.HealthError,
            "^" + code + "$",
        ):

            self.verify(**kwargs)

    def test_parse_running_state(self):

        raw = (
            "LoadState=loaded\n"
            "ActiveState=active\n"
            "SubState=running\n"
            "MainPID=1234\n"
            "ControlPID=0\n"
            "UnitFileState=enabled\n"
        )

        self.assertEqual(
            health.parse_service(raw),
            RUNNING,
        )

    def test_duplicate_property_rejected(self):

        with self.assertRaisesRegex(
            health.HealthError,
            "^INVALID_SYSTEMD_PROPERTY$",
        ):

            health.parse_service(
                "MainPID=1\nMainPID=2\n"
            )

    def test_incomplete_state_rejected(self):

        with self.assertRaisesRegex(
            health.HealthError,
            "^INCOMPLETE_SYSTEMD_STATE$",
        ):

            health.parse_service(
                "ActiveState=active\n"
            )

    def test_stopped_confirmed(self):

        self.assertTrue(
            health.is_stopped(
                lambda: STOPPED,
                lambda: (),
            )
        )

    def test_removed_unit_stopped(self):

        self.assertTrue(
            health.is_stopped(
                lambda: REMOVED,
                lambda: (),
            )
        )

    def test_enabled_unit_not_stopped(self):

        enabled = health.ServiceState(
            "loaded", "inactive", "dead",
            0, 0, "enabled",
        )

        self.assertFalse(
            health.is_stopped(
                lambda: enabled,
                lambda: (),
            )
        )

    def test_remaining_process_blocks(self):

        self.assertFalse(
            health.is_stopped(
                lambda: STOPPED,
                lambda: (4321,),
            )
        )

    def test_restart_during_stop_probe(self):

        state = mock.Mock(
            side_effect=[STOPPED, RUNNING]
        )

        self.assertFalse(
            health.is_stopped(
                state,
                lambda: (),
            )
        )

    def test_healthy_service(self):

        result = self.verify()

        self.assertEqual(
            result["health"], "PASS"
        )

        self.assertEqual(
            result["binary_sha256"], SHA256
        )

    def test_incorrect_running_hash(self):

        self.rejected(
            "RUNNING_BINARY_HASH_MISMATCH",
            prove=lambda pid, path: (
                TOKEN, "b" * 64
            ),
        )

    def test_http_failure(self):

        self.rejected(
            "TVH_HTTP_NOT_CONFIRMED",
            api_get=lambda *a, **k: (
                False, 401, None, ""
            ),
        )

    def test_htsp_failure(self):

        self.rejected(
            "TVH_HTSP_UNAVAILABLE",
            htsp_probe=mock.Mock(
                side_effect=OSError(
                    "connection refused"
                )
            ),
        )

    def test_service_pid_changed(self):

        restarted = health.ServiceState(
            "loaded", "active", "running",
            5678, 0, "enabled",
        )

        self.rejected(
            "SERVICE_STATE_CHANGED",
            read_state=mock.Mock(
                side_effect=[
                    RUNNING, restarted
                ],
            ),
        )

    def test_process_identity_changed(self):

        self.rejected(
            "PROCESS_IDENTITY_CHANGED",
            token=lambda pid, path: (
                1234, 101, 1, 10, 20, 30, 40
            ),
        )

    def test_api_exception(self):

        self.rejected(
            "TVH_HTTP_UNAVAILABLE",
            api_get=mock.Mock(
                side_effect=OSError(
                    "API unavailable"
                ),
            ),
        )

    def test_real_proc_executable(self):

        executable = Path(
            sys.executable
        ).resolve()

        observed_token, digest = (
            health.prove_process(
                os.getpid(),
                executable,
            )
        )

        expected = hashlib.sha256(
            executable.read_bytes()
        ).hexdigest()

        self.assertEqual(digest, expected)

        self.assertEqual(
            observed_token,
            health.process_token(
                os.getpid(),
                executable,
            ),
        )

    def test_real_proc_wrong_executable(self):

        with self.assertRaisesRegex(
            health.HealthError,
            "^RUNNING_BINARY_MISMATCH$",
        ):

            health.process_token(
                os.getpid(),
                Path(__file__),
            )


if __name__ == "__main__":
    unittest.main()
