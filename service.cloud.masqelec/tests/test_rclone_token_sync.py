# -*- coding: utf-8 -*-
"""Regresión OAuth de 4 remotos sin Kodi, red o tokens reales."""
import contextlib
import importlib.util
import io
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
        # Guardar la implementación real para ensayar /proc con procesos
        # simulados. Los otros tests aíslan el entorno sin montajes.
        self._real_mount_guard = self.sync._config_mounts_active
        self.sync._config_mounts_active = lambda: False
        # Ningún test unitario ejecuta rclone ni consulta la red.
        self.sync._master_probe_local = lambda raw, names: {
            name: "ok" for name in names
        }

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
        with open(self.path + ".pre-recovery", "rb") as stream:
            self.assertEqual(stream.read(), self.local)

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



    def _set_bad_local(self, bad):
        with open(self.path, "wb") as out:
            out.write(bad)
        old = time.time() - 30
        os.utime(self.path, (old, old))

    def _master_setup(self, published=None, probe_status="ok"):
        self.sync.device_utils.is_master_device = lambda: True
        self.sync._remote_config = lambda key: (published if published is not None
                                                else self.local)
        self.sync._probe = lambda name, config: probe_status

    def _master_backup_files(self):
        prefix = os.path.basename(self.path) + ".pre-master-recovery-"
        return [os.path.join(self.tmp.name, name)
                for name in os.listdir(self.tmp.name) if name.startswith(prefix)]

    def test_master_corrupt_config_requires_two_observations(self):
        damaged = b"[series]\ntype = onedrive\ntoken = {broken-json\n"
        self._set_bad_local(damaged)
        self._master_setup()
        self.assertEqual(self.sync._master_cycle(5000), "master_corrupt_pending")
        self.assertEqual(self._disk(), damaged)
        self.assertEqual(self._master_backup_files(), [])
        self.assertEqual(self.sync._master_cycle(5020), "master_corrupt_pending")
        self.assertEqual(self._disk(), damaged)

    def test_master_corrupt_config_restored_after_confirmation_with_backup(self):
        damaged = self.local.replace(
            b'"refresh_token": "old-one"', b'"refresh_token": {broken'
        )
        self._set_bad_local(damaged)
        self._master_setup()
        with mock.patch.object(self.sync.catalog_utils, "_upload_file") as upload:
            self.assertEqual(self.sync._master_cycle(5000), "master_corrupt_pending")
            self.assertEqual(self.sync._master_cycle(5061),
                             "master_recovered_restart_pending")
            upload.assert_not_called()
        self.assertEqual(self._disk(), self.local)
        backups = self._master_backup_files()
        self.assertEqual(len(backups), 1)
        with open(backups[0], "rb") as stream:
            self.assertEqual(stream.read(), damaged)
        self.assertEqual(os.stat(backups[0]).st_mode & 0o777, 0o600)
        self.assertEqual(os.stat(self.path).st_mode & 0o777, 0o600)

    def test_master_truncated_three_remotes_restored_from_reserve(self):
        damaged = self.local.split(b"[logs]")[0]
        self._set_bad_local(damaged)
        self._master_setup()
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_recovered_restart_pending")
        self.assertEqual(self._disk(), self.local)

    def test_master_missing_config_recovers_without_backup(self):
        os.unlink(self.path)
        self._master_setup()
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_recovered_restart_pending")
        self.assertEqual(self._disk(), self.local)
        self.assertEqual(self._master_backup_files(), [])

    def test_master_corrupt_identity_drift_is_blocked(self):
        damaged = self.local.replace(b"drive_id = id-series",
                                     b"drive_id = wrong-drive")
        damaged = damaged.replace(
            b'"refresh_token": "old-two"', b'"refresh_token": {broken'
        )
        self._set_bad_local(damaged)
        self._master_setup()
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_identity_mismatch")
        self.assertEqual(self._disk(), damaged)
        self.assertEqual(self._master_backup_files(), [])

    def test_master_corrupt_recovery_rejects_invalid_published_layout(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup(published=b"[series]\ntype = drive\n")
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        with self.assertRaises(ValueError):
            self.sync._master_cycle(1061)
        self.assertEqual(self._disk(), damaged)

    def test_master_corrupt_recovery_rejects_unavailable_candidate(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup(probe_status="unavailable")
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_candidate_unverified")
        self.assertEqual(self._disk(), damaged)
        self.assertEqual(self._master_backup_files(), [])

    def test_master_authorization_error_repairs_only_onedrive_token(self):
        published = _mixed(series_refresh="new-one")
        self._master_setup(published=published)
        self.sync._master_probe_local = lambda local, names: {
            name: ("auth" if name == "series" else "ok") for name in names
        }
        with mock.patch.object(self.sync.catalog_utils, "_upload_file") as upload:
            self.assertEqual(self.sync._master_cycle(1000),
                             "master_recovered_restart_pending")
            upload.assert_not_called()
        repaired = self._disk()
        self.assertEqual(policy.oauth_tokens(repaired)["series"]["refresh_token"],
                         "new-one")
        for name in ("movies", "update", "logs"):
            self.assertEqual(policy.oauth_tokens(repaired)[name],
                             policy.oauth_tokens(self.local)[name])
        self.assertEqual(len(self._master_backup_files()), 1)

    def test_master_auth_with_same_refresh_different_access_can_repair(self):
        published = self.local.replace(b"access-series", b"valid-access")
        self._master_setup(published=published)
        self.sync._master_probe_local = lambda local, names: {
            name: ("auth" if name == "series" else "ok") for name in names
        }
        self.assertEqual(self.sync._master_cycle(1000),
                         "master_recovered_restart_pending")
        self.assertIn(b"valid-access", self._disk())

    def test_master_auth_when_published_same_token_does_not_overwrite(self):
        self._master_setup()
        self.sync._master_probe_local = lambda local, names: {
            name: ("auth" if name == "series" else "ok") for name in names
        }
        self.assertEqual(self.sync._master_cycle(1000), "no_new_token")
        self.assertEqual(self._disk(), self.local)
        self.assertEqual(self._master_backup_files(), [])

    def test_master_auth_rate_limit_not_treated_as_auth(self):
        self._master_setup()
        self.sync._remote_config = lambda key: self.fail("No descargar reserva")
        self.sync._master_probe_local = lambda local, names: {
            name: "unavailable" for name in names
        }
        with mock.patch.object(self.sync, "_publish_master", return_value="unchanged"):
            self.assertEqual(self.sync._master_cycle(1000), "unchanged")
        self.assertEqual(self._disk(), self.local)

    def test_master_recovery_detects_concurrent_write(self):
        self._master_setup()
        self.sync._remote_config = lambda key: self.local
        self.sync._probe = lambda name, config: "ok"
        old = self.local
        actual = self.local.replace(b"old-one", b"concurrent")
        with open(self.path, "wb") as stream:
            stream.write(actual)
        with mock.patch.object(self.sync, "_read_damaged_snapshot",
                               return_value=actual):
            self.assertEqual(
                self.sync._master_recover("corrupt", original=old),
                "local_changed")
        self.assertEqual(self._disk(), actual)

    def test_master_stale_reserve_auth_failure_keeps_local(self):
        published = _mixed(series_refresh="older-broken")
        self._master_setup(published=published, probe_status="auth")
        self.sync._master_probe_local = lambda raw, names: {
            name: ("auth" if name == "series" else "ok") for name in names
        }
        self.assertEqual(self.sync._master_cycle(1000),
                         "master_candidate_unverified")
        self.assertEqual(self._disk(), self.local)
        self.assertEqual(self._master_backup_files(), [])

    def test_master_second_failure_respects_recovery_cooldown(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup(probe_status="unavailable")
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_candidate_unverified")
        self.assertEqual(self.sync._master_cycle(1121),
                         "master_recovery_cooldown")
        self.assertEqual(self._disk(), damaged)

    def test_master_corrupt_symlink_is_not_replaced(self):
        os.unlink(self.path)
        outside = os.path.join(self.tmp.name, "outside.conf")
        with open(outside, "wb") as stream:
            stream.write(b"SECRET_TEST")
        os.symlink(outside, self.path)
        self._master_setup()
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_unsafe")
        self.assertEqual(self.sync._master_cycle(1061), "master_corrupt_unsafe")
        with open(outside, "rb") as stream:
            self.assertEqual(stream.read(), b"SECRET_TEST")


    def test_master_corrupt_google_rate_limit_does_not_block_onedrive(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup()
        def fake_probe(name, config):
            return "rate_limited" if name in ("update", "logs") else "ok"
        self.sync._probe = fake_probe
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_recovered_restart_pending")
        self.assertEqual(self._disk(), self.local)
        self.assertEqual(len(self._master_backup_files()), 1)

    def test_master_corrupt_onedrive_rate_limit_blocks_restore(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup()
        self.sync._probe = lambda name, config: (
            "rate_limited" if name == "series" else "ok"
        )
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_candidate_unverified")
        self.assertEqual(self._disk(), damaged)

    def test_master_corrupt_google_auth_failure_blocks_restore(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup()
        self.sync._probe = lambda name, config: (
            "auth" if name == "update" else "ok"
        )
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_candidate_unverified")
        self.assertEqual(self._disk(), damaged)

    def test_probe_distinguishes_rate_limit_from_oauth_failure(self):
        response = types.SimpleNamespace(
            returncode=1, stderr=b"Too Many Requests, rate limit exceeded"
        )
        with mock.patch.object(self.sync.subprocess, "run", return_value=response):
            self.assertEqual(self.sync._probe("series", self.path), "rate_limited")
        response.stderr = b"failed to refresh token: invalid_grant"
        with mock.patch.object(self.sync.subprocess, "run", return_value=response):
            self.assertEqual(self.sync._probe("series", self.path), "auth")



    def _six_section_config(self):
        return (self.local +
                b"\n[alias]\ntype = alias\nremote = series:\n"
                b"\n[crypt]\ntype = crypt\nremote = movies:media\n"
                b"password = test-only-opaque\n")

    def test_master_six_sections_publish_keeps_auxiliary_remotes(self):
        local = self._six_section_config()
        self._set_bad_local(local)
        published = local.replace(b"old-one", b"former-one")
        self._master_setup(published=published, probe_status="ok")
        payloads = []
        def upload(token, src, dest):
            with open(src, "rb") as fd:
                payloads.append(fd.read())
            return True
        self.sync.catalog_utils._upload_file = upload
        self.assertEqual(self.sync._publish_master(), "published")
        self.assertEqual(self._disk(), local)
        self.assertEqual(len(payloads), 1)
        self.assertIn(b"[alias]", local)
        self.assertIn(b"[crypt]", local)

    def test_master_six_sections_corrupt_then_restore_every_section(self):
        local = self._six_section_config()
        self._set_bad_local(local)
        self._master_setup(published=local, probe_status="ok")
        damaged = local.replace(
            b'"refresh_token": "old-one"', b'"refresh_token": {broken'
        )
        self._set_bad_local(damaged)
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_recovered_restart_pending")
        self.assertEqual(self._disk(), local)
        self.assertEqual(len(policy.sections(self._disk())), 6)
        backup = self._master_backup_files()
        self.assertEqual(len(backup), 1)
        with open(backup[0], "rb") as stream:
            self.assertEqual(stream.read(), damaged)

    def test_master_six_sections_different_extra_identity_blocks_recovery(self):
        local = self._six_section_config()
        damaged = local.replace(b"remote = series:",
                                b"remote = another-remote:")
        damaged = damaged.replace(
            b'"refresh_token": "old-one"', b'"refresh_token": {broken'
        )
        self._set_bad_local(damaged)
        self._master_setup(published=local, probe_status="ok")
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061),
                         "master_identity_mismatch")
        self.assertEqual(self._disk(), damaged)


    def test_master_mounts_active_blocks_corrupt_restore_before_network(self):
        damaged = b"broken-config-while-mount-alive"
        self._set_bad_local(damaged)
        self._master_setup()
        self.sync._config_mounts_active = lambda: True
        self.sync._remote_config = lambda key: self.fail("No remote download")
        self.assertEqual(self.sync._master_cycle(1000), "master_corrupt_pending")
        self.assertEqual(self.sync._master_cycle(1061), "mounts_active")
        self.assertEqual(self._disk(), damaged)
        self.assertEqual(self._master_backup_files(), [])

    def test_master_mounts_active_blocks_oauth_restore(self):
        self._master_setup(published=_mixed(series_refresh="new-one"))
        self.sync._config_mounts_active = lambda: True
        self.sync._remote_config = lambda key: self.fail("No remote download")
        self.sync._master_probe_local = lambda raw, names: {
            name: ("auth" if name == "series" else "ok") for name in names
        }
        self.assertEqual(self.sync._master_cycle(1000), "mounts_active")
        self.assertEqual(self._disk(), self.local)
        self.assertEqual(self._master_backup_files(), [])

    def test_client_mounts_active_blocks_install(self):
        self.sync._config_mounts_active = lambda: True
        self.sync._remote_config = lambda key: self.fail("No remote download")
        self.sync._probe = lambda name, path: (
            "auth" if name == "series" else "ok")
        self.assertEqual(self.sync._recover_client(), "mounts_active")
        self.assertEqual(self._disk(), self.local)
        self.assertFalse(os.path.exists(self.path + ".pre-recovery"))

    def test_master_mount_starts_during_probe_blocks_replace(self):
        damaged = b"truncated"
        self._set_bad_local(damaged)
        self._master_setup()
        checks = []
        def becomes_busy():
            checks.append(True)
            return len(checks) >= 2
        self.sync._config_mounts_active = becomes_busy
        self.assertEqual(
            self.sync._master_recover("corrupt", original=damaged),
            "mounts_active")
        self.assertEqual(self._disk(), damaged)
        self.assertEqual(self._master_backup_files(), [])

    def test_client_mount_starts_after_candidate_validation_blocks_replace(self):
        self.sync._remote_config = lambda key: _mixed(series_refresh="new-one")
        self.sync._probe = lambda name, path: (
            "auth" if name == "series" and "pre-recovery" not in path
            else "ok"
        )
        counts = []
        def guard():
            counts.append(True)
            return len(counts) >= 2
        self.sync._config_mounts_active = guard
        # El primer sondeo usa una copia .rclone-recovery; distinguiéndolo por
        # el contenido podemos simular AUTH original y OK del candidato.
        def probe(name, path):
            if name != "series":
                return "ok"
            with open(path, "rb") as fd:
                token = policy.oauth_tokens(fd.read())["series"]
            return "auth" if token["refresh_token"] == "old-one" else "ok"
        self.sync._probe = probe
        self.assertEqual(self.sync._recover_client(), "mounts_active")
        self.assertEqual(self._disk(), self.local)
        self.assertFalse(os.path.exists(self.path + ".pre-recovery"))

    def test_same_bytes_replaced_in_other_inode_blocks_master_restore(self):
        self._master_setup()
        self.sync._remote_config = lambda key: self.local
        changed = []
        def change_at_probe(name, conf):
            if not changed:
                replacement = self.sync._write_candidate(self.path, self.local)
                os.replace(replacement, self.path)
                changed.append(True)
            return "ok"
        self.sync._probe = change_at_probe
        self.assertEqual(self.sync._master_recover("corrupt", original=self.local),
                         "local_changed")
        self.assertEqual(self._disk(), self.local)
        self.assertEqual(self._master_backup_files(), [])

    def test_same_bytes_replaced_in_other_inode_blocks_client_restore(self):
        self.sync._remote_config = lambda key: _mixed(series_refresh="new-one")
        changed = []
        def probe(name, conf):
            if name != "series":
                return "ok"
            with open(conf, "rb") as fd:
                current = policy.oauth_tokens(fd.read())["series"]["refresh_token"]
            if current == "old-one":
                return "auth"
            if not changed:
                replacement = self.sync._write_candidate(self.path, self.local)
                os.replace(replacement, self.path)
                changed.append(True)
            return "ok"
        self.sync._probe = probe
        self.assertEqual(self.sync._recover_client(), "local_changed")
        self.assertEqual(self._disk(), self.local)

    def test_master_upload_detects_subsequent_token_rotation(self):
        previous = _mixed(series_refresh="older-one")
        self._master_setup(published=previous)
        self.sync._probe = lambda name, conf: "ok"
        def upload(token, src, dest):
            refreshed = self.local.replace(b"old-one", b"newer-one")
            with open(self.path, "wb") as fd:
                fd.write(refreshed)
            return True
        self.sync.catalog_utils._upload_file = upload
        self.assertEqual(self.sync._publish_master(), "published_local_advanced")
        self.assertIn(b"newer-one", self._disk())

    def test_master_retry_when_local_rotates_during_upload(self):
        previous = _mixed(series_refresh="older-one")
        self._master_setup(published=previous)
        self.sync._probe = lambda name, conf: "ok"
        calls = []
        def upload(token, src, dest):
            calls.append(True)
            if len(calls) == 1:
                rotated = self.local.replace(b"old-one", b"newer-one")
                with open(self.path, "wb") as fd:
                    fd.write(rotated)
            return True
        self.sync.catalog_utils._upload_file = upload
        self.assertEqual(self.sync._master_cycle(1000), "published_local_advanced")
        self.assertIsNone(self.sync._last_master_confirmed_fp)
        # Tras estabilizarse el fichero, la rotación vuelve a publicarse.
        os.utime(self.path, (time.time() - 30, time.time() - 30))
        self.assertEqual(self.sync._master_cycle(1061), "published")
        self.assertEqual(len(calls), 2)



    def _simulate_processes(self, commands):
        class Scan:
            def __init__(self, entries):
                self.entries = entries
            def __iter__(self):
                return iter(self.entries)
            def close(self):
                pass
        entries = [types.SimpleNamespace(name=str(i + 2000),
                                         path="/proc/{}".format(i + 2000))
                   for i in range(len(commands))]
        by_path = {entries[i].path + "/cmdline": (b"\0".join(
            word.encode("utf-8") for word in argv) + b"\0")
                   for i, argv in enumerate(commands)}
        def open_proc(path, mode="rb"):
            return io.BytesIO(by_path[path])
        return (mock.patch.object(self.sync.os, "scandir",
                                  return_value=Scan(entries)),
                mock.patch("builtins.open", side_effect=open_proc),
                mock.patch.object(self.sync.os, "getpid",
                                  return_value=999999))

    def test_detects_one_of_four_rclone_mount_writers(self):
        argv = [["/storage/.config/rclone/rclone", "mount", "cloud:tv",
                 "/storage/.mnt/one", "--config", "/other/rclone.conf"],
                ["/storage/.config/rclone/rclone", "mount", "cloud:movies",
                 "/storage/.mnt/two", "--config", self.path],
                ["/storage/.config/rclone/rclone", "mount", "cloud:shows",
                 "/storage/.mnt/three", "--config", "/other/rclone.conf"],
                ["/storage/.config/rclone/rclone", "lsf", "cloud:",
                 "--config", self.path]]
        contexts = self._simulate_processes(argv)
        with contexts[0], contexts[1], contexts[2]:
            self.assertTrue(self._real_mount_guard())

    def test_different_rclone_mount_config_does_not_block_lab(self):
        commands = [["/storage/.config/rclone/rclone", "mount", "cloud:",
                     "/storage/.mnt/a",
                     "--config=/storage/.config/rclone/rclone.conf"]]
        contexts = self._simulate_processes(commands)
        with contexts[0], contexts[1], contexts[2]:
            self.assertFalse(self._real_mount_guard())

    def test_rclone_mount_without_explicit_config_fails_closed(self):
        commands = [["rclone", "mount", "cloud:", "/storage/.mnt/a"]]
        contexts = self._simulate_processes(commands)
        with contexts[0], contexts[1], contexts[2]:
            self.assertTrue(self._real_mount_guard())



    def test_two_fuse_mode_never_publishes_stale_legacy_tokens(self):
        self.sync.device_utils.is_master_device = lambda: True
        with mock.patch.object(
                self.sync.rclone_two_mount_rollout, "mode",
                return_value="active"):
            with mock.patch.object(self.sync, "_remote_config") as remote:
                self.assertEqual(self.sync._publish_master(), "two_mount_mode")
                remote.assert_not_called()
            self.assertEqual(self._disk(), self.local)

    def test_two_fuse_mode_blocks_master_and_client_legacy_restore(self):
        self.sync.device_utils.is_master_device = lambda: True
        with mock.patch.object(
                self.sync.rclone_two_mount_rollout, "mode",
                return_value="active"):
            self.assertEqual(
                self.sync._master_recover("corrupt", original=b"broken"),
                "two_mount_mode")
            self.assertEqual(self.sync._master_cycle(1000), "two_mount_mode")
            self.assertEqual(self.sync._recover_client(), "two_mount_mode")
            self.assertEqual(self._disk(), self.local)

    def test_two_fuse_mode_tick_no_legacy_probe_or_publish(self):
        self.sync.constants.RCLONE_TOKEN_SYNC_ENABLED = True
        self.addCleanup(
            setattr, self.sync.constants, "RCLONE_TOKEN_SYNC_ENABLED", False)
        self.sync.device_utils.get_device_role = lambda: "MASTER"
        with mock.patch.object(
                self.sync.rclone_two_mount_rollout, "mode",
                return_value="active"):
            with mock.patch.object(self.sync, "_master_cycle") as cycle:
                self.sync.tick()
                cycle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
