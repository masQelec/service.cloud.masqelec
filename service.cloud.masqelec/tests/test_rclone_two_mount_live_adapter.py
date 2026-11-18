# -*- coding: utf-8 -*-
"""Adaptador local opcional: pruebas de guardas, sin acceso systemd real."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_plan as plan
from lib import rclone_token_policy as policy
from test_rclone_mount_isolation import wrapped_conf, sample_units


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        root = Path(self.root.name)
        self.units = root / "system.d"
        self.units.mkdir()
        self.config = root / "rclone.conf"
        self.config.write_bytes(wrapped_conf("crypt"))
        self.config.chmod(0o600)
        for name, data in sample_units().items():
            (self.units / name).write_bytes(data)
        self.txn = root / "txn"
        self.marker = root / "mount-mode.json"
        self.accounts = root / "accounts"
        self.actions = []
        self.mountinfo = self.legacy_mountinfo()
        self.adapter = live.LocalAdapter(
            rpc_call=lambda _: '{"jsonrpc":"2.0","id":1,"result":[]}',
            live_enabled=True, canonical=str(self.config),
            unit_dir=str(self.units),
            account_confs=(str(self.accounts / "account1.conf"),
                           str(self.accounts / "account2.conf")),
            state_path=str(self.marker), txn_parent=str(self.txn),
            runner=self.command, mount_reader=lambda:self.mountinfo)

    @staticmethod
    def legacy_mountinfo():
        rows = []
        for k, (_name, _, _, target) in enumerate(
                (("a",1,"movies","/storage/.mnt/videos/1"),
                 ("b",2,"movies","/storage/.mnt/videos/2"),
                 ("c",1,"tvshows","/storage/.mnt/tvshows/1"),
                 ("d",2,"tvshows","/storage/.mnt/tvshows/2"))):
            rows.append("1 0 0:{} / {} rw - fuse.rclone old rw".format(
                30+k, target))
        return "\n".join(rows)

    def command(self, args):
        self.actions.append(tuple(args))
        return True

    def test_disabled_operator_refuses_any_io(self):
        self.adapter.enabled = False
        self.assertEqual(live.execute_with_local_lock(
            self.adapter, authorized=True, verified_rollback=True),
            "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.actions, [])
        self.assertFalse(self.txn.exists())

    def test_no_authorization_refuses(self):
        self.assertEqual(live.execute_with_local_lock(self.adapter),
                         "BLOCKED_NOT_AUTHORIZED")
        self.assertEqual(self.actions, [])

    def test_rollback_gate_refuses(self):
        self.assertEqual(live.execute_with_local_lock(
            self.adapter, authorized=True), "BLOCKED_ROLLBACK_NOT_READY")
        self.assertEqual(self.actions, [])

    def test_legacy_preflight_and_private_prepare(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
        self.assertTrue(Path(self.adapter.txn, "canonical.conf").exists())
        self.assertEqual(journal.phase(self.adapter.txn), "prepared")

    def test_global_feature_flag_blocks_live_mutations(self):
        with mock.patch.object(live.constants,
                               "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False):
            self.assertEqual(live.execute_with_local_lock(
                self.adapter, authorized=True, verified_rollback=True),
                "BLOCKED_FEATURE_DISABLED")
        self.assertFalse(self.txn.exists())
        self.assertEqual(self.actions, [])

    def test_mark_active_disables_legacy_before_enabling_new(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            self.adapter.mark_cutover_started()
            with mock.patch.object(self.adapter, "complete_health",
                                   return_value=True):
                self.adapter.mark_active()
        changes = [x for x in self.actions
                   if x[1] in ("disable", "enable")]
        self.assertEqual(
            changes[:8],
            [("systemctl", "disable", n)
             for n in rollout.LEGACY_SERVICES] * 2)
        self.assertEqual(
            changes[8:],
            [("systemctl", "enable", n)
             for n in rollout.NEW_SERVICES + rollout.BIND_SERVICES])
        self.assertEqual(journal.phase(self.adapter.txn), "active")

    def test_first_enable_failure_no_old_unit_reenabled(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            self.adapter.mark_cutover_started()
            def run(args):
                self.actions.append(tuple(args))
                return args[1] != "enable"
            self.adapter.runner = run
            with mock.patch.object(self.adapter, "complete_health",
                                   return_value=True):
                with self.assertRaises(RuntimeError):
                    self.adapter.mark_active()
        actions = [x for x in self.actions
                   if x[1] in ("disable", "enable")]
        self.assertEqual(
            actions[:8],
            [("systemctl", "disable", n)
             for n in rollout.LEGACY_SERVICES] * 2)
        self.assertEqual(
            actions[8], ("systemctl", "enable", rollout.NEW_SERVICES[0]))
        self.assertFalse(any(x[1] == "enable" and
                             x[2] in rollout.LEGACY_SERVICES
                             for x in actions))

    def test_preflight_refuses_existing_v2_unit(self):
        (self.units / rollout.NEW_SERVICES[0]).write_bytes(b"[Unit]\n")
        self.assertFalse(self.adapter.legacy_preflight())

    def test_preflight_refuses_existing_account_config(self):
        self.accounts.mkdir()
        (self.accounts / "account1.conf").write_bytes(b"old")
        self.assertFalse(self.adapter.legacy_preflight())

    def test_preflight_refuses_stacked_legacy_fuse(self):
        self.mountinfo += "\n" + self.legacy_mountinfo().splitlines()[0]
        self.assertFalse(self.adapter.legacy_preflight())

    def test_recovery_refuses_active_new_writer_without_mount(self):
        def active(args):
            return ("rclone_library_1.service" in args)
        self.adapter.runner = active
        self.assertFalse(self.adapter.new_fully_unmounted())

    def test_preflight_refuses_existing_marker(self):
        self.marker.write_text("{}")
        self.assertFalse(self.adapter.legacy_preflight())

    def test_marker_is_unsafe_before_stopping_legacy(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            self.adapter.mark_cutover_started()
        self.assertEqual(journal.phase(self.adapter.txn),
                         "cutover_started")
        self.assertEqual(rollout.mode(False, str(self.marker)), "unsafe")
        disables = [a for a in self.actions if a[1] == "disable"]
        self.assertEqual(disables,
                         [("systemctl", "disable", unit)
                          for unit in rollout.LEGACY_SERVICES])
        self.assertNotIn(("systemctl", "stop",
                          "rclone_videos_1.service"), self.actions)

    def test_cutover_disables_legacy_before_stop_and_is_journaled(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            self.adapter.mark_cutover_started()
        self.assertEqual(journal.phase(self.adapter.txn),
                         "cutover_started")
        ops = [a for a in self.actions if a[1] in ("disable", "stop")]
        self.assertEqual(ops, [
            ("systemctl", "disable", unit)
            for unit in rollout.LEGACY_SERVICES])
        self.assertTrue(self.marker.exists())

    def test_mount_guard_identifies_old_and_new(self):
        self.assertTrue(self.adapter._old_mounted())
        self.adapter.runner = lambda args: False
        self.assertTrue(self.adapter.new_fully_unmounted())
        self.mountinfo += (
            "\n20 1 0:9 / /storage/.mnt/cloud/1 rw - fuse.rclone new rw")
        self.assertFalse(self.adapter.new_fully_unmounted())

    def test_mount_guard_detects_v2_bind_in_old_target(self):
        self.adapter.runner = lambda args: False
        self.mountinfo = (
            "20 1 0:8 /movies /storage/.mnt/videos/1 rw "
            "- fuse.rclone new rw")
        self.assertFalse(self.adapter.new_fully_unmounted())

    def test_kodi_playback_must_be_empty(self):
        self.assertTrue(self.adapter.playback_still_idle())
        self.adapter.rpc = lambda _: '{"jsonrpc":"2.0","id":1,"result":[{"playerid":1,"type":"video"}]}'
        self.assertFalse(self.adapter.playback_still_idle())

    def test_health_refuses_without_two_known_media(self):
        self.adapter.mountinfo = self.legacy_mountinfo
        self.assertFalse(self.adapter._known_media_verified())

    def test_known_media_rejects_non_kodi_paths_without_open(self):
        self.adapter.known_media_files = (
            "/tmp/fake/movie.mkv", "/storage/.mnt/videos/2/film.mkv")
        with mock.patch.object(self.adapter, "_probe_known_media",
                               side_effect=AssertionError("must not probe")):
            self.assertFalse(self.adapter._known_media_verified())

    def test_known_media_rejects_path_traversal(self):
        self.adapter.known_media_files = (
            "/storage/.mnt/videos/1/../other.mkv",
            "/storage/.mnt/videos/2/a.mkv")
        with mock.patch.object(self.adapter, "_probe_known_media",
                               side_effect=AssertionError("must not probe")):
            self.assertFalse(self.adapter._known_media_verified())

    def test_known_media_reads_one_byte_per_account(self):
        self.adapter.known_media_files = (
            "/storage/.mnt/videos/1/one.mkv",
            "/storage/.mnt/tvshows/2/two.mkv")
        with mock.patch.object(self.adapter, "_probe_known_media",
                               return_value=True) as probe:
            self.assertTrue(self.adapter._known_media_verified())
        self.assertEqual(probe.call_count, 2)

    def test_known_media_empty_file_fails(self):
        self.adapter.known_media_files = (
            "/storage/.mnt/videos/1/one.mkv",
            "/storage/.mnt/tvshows/2/two.mkv")
        with mock.patch.object(self.adapter, "_probe_known_media",
                               return_value=False):
            self.assertFalse(self.adapter._known_media_verified())

    def test_bounded_media_subprocess_uses_no_shell_and_one_byte(self):
        class Done:
            returncode = 0
        with mock.patch.object(live.shutil, "which",
                               return_value="/usr/bin/python3"), \
             mock.patch.object(live.subprocess, "run",
                               return_value=Done()) as run:
            self.assertTrue(self.adapter._probe_known_media(
                "/storage/.mnt/videos/1/film.mkv"))
        argv = run.call_args.args[0]
        self.assertEqual(argv[0], "/usr/bin/python3")
        self.assertEqual(argv[1], "-c")
        self.assertEqual(argv[3], "/storage/.mnt/videos/1/film.mkv")
        self.assertEqual(run.call_args.kwargs["timeout"], 15)
        self.assertFalse(run.call_args.kwargs["check"])

    def test_media_timeout_blocks(self):
        with mock.patch.object(live.shutil, "which",
                               return_value="/usr/bin/python3"), \
             mock.patch.object(live.subprocess, "run",
                               side_effect=live.subprocess.TimeoutExpired(
                                   "probe", 15)):
            self.assertFalse(self.adapter._probe_known_media(
                "/storage/.mnt/videos/1/film.mkv"))

    def test_missing_python3_blocks_probe(self):
        with mock.patch.object(live.shutil, "which", return_value=None):
            self.assertFalse(self.adapter._probe_known_media(
                "/storage/.mnt/videos/1/film.mkv"))

    def test_canonical_unmodified_and_candidate_staged_on_token_change(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            journal.transition(self.adapter.txn, "prepared", "cutover_started")
            original = self.config.read_bytes()
            updated = original.replace(
                b"refresh-users_library_1", b"offline-rotated-refresh")
            self.assertNotEqual(original, updated)
            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                self.adapter._rewrite_canonical_if_stable(original, updated)
            self.assertEqual(self.config.read_bytes(), original)
            staged = Path(self.adapter.txn,
                          "canonical-recovery-candidate.conf")
            self.assertEqual(staged.read_bytes(), updated)
            self.assertEqual(staged.stat().st_mode & 0o777, 0o600)

    def test_canonical_same_bytes_is_noop_without_candidate(self):
        original = self.config.read_bytes()
        self.adapter._rewrite_canonical_if_stable(original, original)
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse(self.txn.exists())

    def test_canonical_concurrent_change_blocks_staging(self):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            journal.transition(self.adapter.txn, "prepared", "cutover_started")
            old = self.config.read_bytes()
            self.config.write_bytes(old + b"\n# concurrent\n")
            with self.assertRaisesRegex(ValueError, "Canonical changed"):
                self.adapter._rewrite_canonical_if_stable(old, old)
            self.assertFalse(Path(
                self.adapter.txn,
                "canonical-recovery-candidate.conf").exists())

    def test_no_canonical_replace_in_adapter_source(self):
        code = (Path(__file__).resolve().parents[1] /
                "lib/rclone_two_mount_live_adapter.py").read_text()
        start = code.index("def _rewrite_canonical_if_stable")
        end = code.index("def reconcile_and_restore_legacy", start)
        text = code[start:end]
        self.assertNotIn("os.replace(", text)
        self.assertNotIn("os.rename(", text)
        self.assertIn("canonical-recovery-candidate.conf", text)

    def _prepare_reconcile_context(self, *, rotated=False):
        self.assertTrue(self.adapter.legacy_preflight())
        with journal.locked(str(self.txn)):
            self.assertTrue(self.adapter.prepare_durable_rollback())
            journal.transition(self.adapter.txn, "prepared", "cutover_started")
        original = self.config.read_bytes()
        self.adapter.at_stop = original
        self.accounts.mkdir(mode=0o700)
        for i in (0, 1):
            raw = plan.account_snapshot(original, i)
            if rotated and i == 0:
                raw = raw.replace(b"refresh-users_library_1",
                                  b"ROTATED-ONEDRIVE-ACCOUNT-1")
                self.assertIn(b"ROTATED-ONEDRIVE-ACCOUNT-1", raw)
            path = Path(self.adapter.account_confs[i])
            path.write_bytes(raw)
            path.chmod(0o600)
        return original

    def test_integrated_rollback_stages_refreshed_oauth_but_does_not_write_shared(self):
        original = self._prepare_reconcile_context(rotated=True)
        with journal.locked(str(self.txn)):
            with self.assertRaisesRegex(RuntimeError, "manual recovery"):
                self.adapter.reconcile_and_restore_legacy()
        self.assertEqual(self.config.read_bytes(), original)
        self.assertEqual(journal.phase(self.adapter.txn), "rollback_required")
        candidate = Path(self.adapter.txn,
                         "canonical-recovery-candidate.conf")
        self.assertTrue(candidate.is_file())
        self.assertEqual(candidate.stat().st_mode & 0o777, 0o600)
        content = candidate.read_bytes()
        self.assertIn(b"ROTATED-ONEDRIVE-ACCOUNT-1", content)
        self.assertEqual(
            policy.oauth_tokens(content)["updater"],
            policy.oauth_tokens(original)["updater"])
        self.assertEqual(
            policy.oauth_tokens(content)["logs"],
            policy.oauth_tokens(original)["logs"])

    def test_integrated_rollback_without_token_rotation_leaves_canonical_intact(self):
        original = self._prepare_reconcile_context(rotated=False)
        with journal.locked(str(self.txn)):
            self.adapter.reconcile_and_restore_legacy()
        self.assertEqual(self.config.read_bytes(), original)
        self.assertFalse(Path(
            self.adapter.txn, "canonical-recovery-candidate.conf").exists())
        self.assertEqual(journal.phase(self.adapter.txn), "rollback_required")

    def test_known_systemctl_commands_only(self):
        with self.assertRaises(ValueError):
            self.adapter._systemctl("restart","rclone_videos_1.service")
        with self.assertRaises(ValueError):
            self.adapter._systemctl("stop","other.service")
        self.assertEqual(self.actions, [])

    def test_real_apply_is_not_exposed_from_addon_service(self):
        src = (Path(__file__).resolve().parents[1] /
               "service.py").read_text()
        self.assertNotIn("rclone_two_mount_live_adapter", src)


if __name__ == "__main__":
    unittest.main()
