# -*- coding: utf-8 -*-
"""Regresión OAuth de 4 remotos sin Kodi, red o tokens reales."""
import contextlib
import importlib.util
import json
import os
import sys
import time
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lib
from lib import rclone_token_policy as policy


def _mixed(series_refresh="old-one", movie_refresh="old-two",
           g1_refresh="old-three", g2_refresh="old-four"):
    remotes = (
        ("series", "onedrive", series_refresh, "id-series"),
        ("movies", "onedrive", movie_refresh, "id-movies"),
        ("update", "drive", g1_refresh, None),
        ("logs", "drive", g2_refresh, None),
    )
    result = []
    for name, backend, refresh, drive_id in remotes:
        token = json.dumps({"access_token": "access-" + name,
                            "refresh_token": refresh,
                            "expiry": "2026-11-17T09:00:00Z"})
        section = ["[{}]".format(name), "type = " + backend,
                   "client_id = shared-app",
                   "token = " + token]
        if drive_id:
            section.extend(["drive_id = " + drive_id, "drive_type = personal"])
        result.extend(section + [""])
    return "\n".join(result).encode("utf-8")


def _module():
    """Carga el worker con dependencias Kodi sustituidas localmente."""
    fake_log = types.SimpleNamespace(write_log=lambda *args, **kw: None)
    fake_catalog = types.SimpleNamespace(
        _gh_get_plain_token=lambda: "unused-fake-gh",
        _upload_file=lambda *args: True,
    )
    fake_device = types.SimpleNamespace(
        is_master_device=lambda: False,
        get_key_from_authorized_keys=lambda: b"K" * 32,
        get_device_role=lambda: "CLIENT",
    )
    fake_rclone_utils = types.SimpleNamespace(which_rclone=lambda: "/usr/bin/rclone")
    stubs = {
        "log_utils": fake_log, "catalog_utils": fake_catalog,
        "device_utils": fake_device, "rclone_utils": fake_rclone_utils,
    }
    with contextlib.ExitStack() as stack:
        for name, fake in stubs.items():
            stack.enter_context(mock.patch.object(lib, name, fake, create=True))
        spec = importlib.util.spec_from_file_location(
            "_masqelec_sync_under_test", ROOT / "lib" / "rclone_token_sync.py"
        )
        subject = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(subject)
    return subject


class RcloneTokenSyncTests(unittest.TestCase):
    def setUp(self):
        self.sync = _module()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "rclone.conf")
        self.local = _mixed()
        with open(self.path, "wb") as out:
            out.write(self.local)
        # El archivo de pruebas tiene que superar el debounce del MASTER.
        old = time.time() - 30
        os.utime(self.path, (old, old))
        self.sync.CONF_PATH = self.path
        self.sync.REMOTE_PATH = "rclone/rclone.conf.crypt"

    def _disk(self):
        with open(self.path, "rb") as stream:
            return stream.read()

    def test_master_skips_access_token_only_change(self):
        remote = self.local.replace(b"access-series", b"previous-access")
        self.sync.device_utils.is_master_device = lambda: True
        self.sync._remote_config = lambda key: remote
        with mock.patch.object(self.sync.catalog_utils, "_upload_file") as upload:
            self.assertEqual(self.sync._publish_master(), "unchanged")
            upload.assert_not_called()

    def test_master_refuses_static_change(self):
        remote = self.local.replace(b"drive_id = id-series",
                                    b"drive_id = altered-drive-id")
        self.sync.device_utils.is_master_device = lambda: True
        self.sync._remote_config = lambda key: remote
        with self.assertRaisesRegex(ValueError, "opciones no OAuth"):
            self.sync._publish_master()

    def test_master_does_not_publish_on_unverified_onedrive(self):
        published = _mixed(series_refresh="previous")
        self.sync.device_utils.is_master_device = lambda: True
        self.sync._remote_config = lambda key: published
        self.sync._probe = lambda name, path: "unavailable"
        with mock.patch.object(self.sync.catalog_utils, "_upload_file") as upload:
            self.assertEqual(self.sync._publish_master(), "candidate_unverified")
            upload.assert_not_called()
        self.assertEqual(self._disk(), self.local)

    def test_master_publishes_only_after_probing_changed_remote(self):
        published = _mixed(series_refresh="previous")
        self.sync.device_utils.is_master_device = lambda: True
        self.sync._remote_config = lambda key: published
        probed = []
        self.sync._probe = lambda name, path: probed.append(name) or "ok"
        sent = []

        def upload(token, src, dest):
            self.assertEqual(dest, "rclone/rclone.conf.crypt")
            self.assertNotEqual(src, self.path)
            with open(src, "rb") as stream:
                sent.append(stream.read())
            return True

        self.sync.catalog_utils._upload_file = upload
        self.assertEqual(self.sync._publish_master(), "published")
        self.assertEqual(probed, ["series"])
        self.assertEqual(len(sent), 1)
        self.assertTrue(sent[0].startswith(b"MQC2:"))
        self.assertEqual(self._disk(), self.local)

    def test_client_repairs_only_failed_onedrive_and_keeps_backup(self):
        published = _mixed(series_refresh="new-one")
        self.sync._remote_config = lambda key: published

        def probe(name, config):
            with open(config, "rb") as stream:
                content = stream.read()
            if name == "series" and (
                    policy.oauth_tokens(content)[name]["refresh_token"] == "old-one"):
                return "auth"
            return "ok"

        self.sync._probe = probe
        self.assertEqual(self.sync._recover_client(), "recovered_restart_pending")
        repaired = self._disk()
        self.assertEqual(policy.oauth_tokens(repaired)["series"]["refresh_token"], "new-one")
        for name in ("movies", "update", "logs"):
            self.assertEqual(policy.oauth_tokens(repaired)[name],
                             policy.oauth_tokens(self.local)[name])
        self.assertEqual(open(self.path + ".pre-recovery", "rb").read(), self.local)

    def test_client_rate_limit_does_not_replace_config(self):
        self.sync._probe = lambda name, config: "unavailable"
        self.assertEqual(self.sync._recover_client(), "unavailable")
        self.assertEqual(self._disk(), self.local)
        self.assertFalse(os.path.exists(self.path + ".pre-recovery"))

    def test_client_failed_candidate_does_not_replace_config(self):
        self.sync._remote_config = lambda key: _mixed(series_refresh="new-one")

        def probe(name, config):
            if name == "series":
                return "auth" if "recovery" not in config else "unavailable"
            return "ok"

        # probe inicial usa copia temporal y puede llevar prefijo recovery:
        # diferenciar por token real, sin depender de nombres de archivos.
        counter = []
        def probe_ordered(name, config):
            if name != "series":
                return "ok"
            counter.append(name)
            return "auth" if len(counter) == 1 else "unavailable"
        self.sync._probe = probe_ordered
        self.assertEqual(self.sync._recover_client(), "candidate_failed")
        self.assertEqual(self._disk(), self.local)

    def test_client_onedrive_mismatched_drive_id_blocked(self):
        published = _mixed(series_refresh="new-one").replace(
            b"drive_id = id-series", b"drive_id = id-other"
        )
        self.sync._remote_config = lambda key: published
        self.sync._probe = lambda name, path: "auth" if name == "series" else "ok"
        self.assertEqual(self.sync._recover_client(), "no_new_token")
        self.assertEqual(self._disk(), self.local)

    def test_first_tick_does_not_wait_for_uptime(self):
        self.sync.constants.RCLONE_TOKEN_SYNC_ENABLED = True
        self.addCleanup(setattr, self.sync.constants, "RCLONE_TOKEN_SYNC_ENABLED", False)
        self.sync.device_utils.get_device_role = lambda: "MASTER"
        status = []
        self.sync._publish_master = lambda: status.append("ran") or "unchanged"
        self.sync._last_tick = None
        with mock.patch.object(self.sync.time, "monotonic", side_effect=[50.0, 50.0, 50.0, 51.0]):
            self.sync.tick()
            self.sync.tick()
        self.assertEqual(status, ["ran"])


    def test_master_does_not_publish_during_live_rclone_write(self):
        self.sync.device_utils.is_master_device = lambda: True
        now = time.time()
        os.utime(self.path, (now, now))
        with mock.patch.object(self.sync, "_remote_config") as remote:
            self.assertEqual(self.sync._publish_master(), "local_settling")
            remote.assert_not_called()

    def test_master_checks_every_minute_without_six_hour_publish_lock(self):
        self.sync.constants.RCLONE_TOKEN_SYNC_ENABLED = True
        self.addCleanup(setattr, self.sync.constants, "RCLONE_TOKEN_SYNC_ENABLED", False)
        self.sync.device_utils.get_device_role = lambda: "MASTER"
        actions = []
        self.sync._publish_master = lambda: actions.append("publish") or "published"
        with mock.patch.object(self.sync.time, "monotonic", return_value=100.0):
            self.sync.tick()
        with mock.patch.object(self.sync.time, "monotonic", return_value=161.0):
            self.sync.tick()
        self.assertEqual(actions, ["publish"])
        # OneDrive renueva refresh_token; el siguiente minuto se publica.
        updated = self.local.replace(b"old-one", b"new-one")
        with open(self.path, "wb") as out:
            out.write(updated)
        with mock.patch.object(self.sync.time, "monotonic", return_value=222.0):
            self.sync.tick()
        self.assertEqual(actions, ["publish", "publish"])

    def test_master_ignores_access_token_only_churn_during_poll(self):
        self.sync.constants.RCLONE_TOKEN_SYNC_ENABLED = True
        self.addCleanup(setattr, self.sync.constants, "RCLONE_TOKEN_SYNC_ENABLED", False)
        self.sync.device_utils.get_device_role = lambda: "MASTER"
        actions = []
        self.sync._publish_master = lambda: actions.append("check") or "unchanged"
        with mock.patch.object(self.sync.time, "monotonic", return_value=100.0):
            self.sync.tick()
        refreshed_access = self.local.replace(b"access-series", b"new-access-only")
        with open(self.path, "wb") as out:
            out.write(refreshed_access)
        with mock.patch.object(self.sync.time, "monotonic", return_value=161.0):
            self.sync.tick()
        self.assertEqual(actions, ["check"])

    def test_master_periodically_reconciles_without_local_changes(self):
        self.sync.constants.RCLONE_TOKEN_SYNC_ENABLED = True
        self.addCleanup(setattr, self.sync.constants, "RCLONE_TOKEN_SYNC_ENABLED", False)
        self.sync.device_utils.get_device_role = lambda: "MASTER"
        actions = []
        self.sync._publish_master = lambda: actions.append("check") or "unchanged"
        with mock.patch.object(self.sync.time, "monotonic", return_value=100.0):
            self.sync.tick()
        with mock.patch.object(self.sync.time, "monotonic", return_value=100.0 + 21601):
            self.sync.tick()
        self.assertEqual(actions, ["check", "check"])



if __name__ == "__main__":
    unittest.main()
