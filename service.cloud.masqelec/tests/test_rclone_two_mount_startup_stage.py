# -*- coding: utf-8 -*-
"""Preparación local sin red, mounts, systemd ni Kodi; fixtures artificiales."""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_startup_stage as stage
from lib import rclone_two_mount_rollout as rollout
from test_rclone_mount_isolation import sample_units, wrapped_conf


class StartupStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.conf = root / "rclone.conf"
        self.units = root / "system.d"
        self.units.mkdir()
        self.parent = root / "private-stage"
        self.state = root / "mount-mode.json"
        self.conf.write_bytes(wrapped_conf("crypt"))
        self.conf.chmod(0o600)
        for name, payload in sample_units().items():
            p = self.units / name
            p.write_bytes(payload)
            p.chmod(0o644)

    def stage(self, **updates):
        args = dict(staging_enabled=True, conf_path=str(self.conf),
                    unit_dir=str(self.units), parent=str(self.parent),
                    state_path=str(self.state))
        args.update(updates)
        return stage.stage_on_startup(**args)

    def staged_folder(self):
        return self.parent / rollout.CANDIDATE_ID

    def test_disabled_avoids_any_filesystem_access(self):
        with mock.patch.object(stage, "_read_sources",
                               side_effect=AssertionError("No file access")):
            result = self.stage(staging_enabled=False)
        self.assertEqual(result, "disabled")
        self.assertFalse(self.parent.exists())

    def test_first_stage_creates_two_private_configs_six_units_manifest(self):
        self.assertEqual(self.stage(), "staged_private_local")
        directory = self.staged_folder()
        self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        files = sorted(p.name for p in directory.iterdir())
        self.assertEqual(len(files), 9)
        self.assertEqual(len([x for x in files if x.endswith(".service")]), 6)
        for name in ("account1.conf", "account2.conf"):
            file = directory / name
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            self.assertIn(b"type = crypt", file.read_bytes())
        manifest = json.loads(
            (directory / "rollout-manifest.json").read_text())
        self.assertEqual(manifest["activation"], "stage_only")
        self.assertFalse(manifest["live_install_allowed"])
        self.assertEqual(manifest["credential_source"],
                         "existing_local_config_unverified")
        self.assertEqual(manifest["rclone_processes"], 2)
        self.assertEqual(len(manifest["unit_sha256"]), 6)

    def test_no_live_config_or_existing_units_modified(self):
        before = self.conf.read_bytes()
        old_units = {name: (self.units / name).read_bytes()
                     for name in rollout.LEGACY_SERVICES}
        self.assertEqual(self.stage(), "staged_private_local")
        self.assertEqual(self.conf.read_bytes(), before)
        for name, raw in old_units.items():
            self.assertEqual((self.units / name).read_bytes(), raw)
        self.assertFalse((self.units / "rclone_library_1.service").exists())

    def test_stage_is_idempotent_with_exact_same_local_snapshot(self):
        self.assertEqual(self.stage(), "staged_private_local")
        p = self.staged_folder() / "account1.conf"
        before = p.stat().st_mtime_ns
        self.assertEqual(self.stage(), "already_staged")
        self.assertEqual(p.stat().st_mtime_ns, before)

    def test_local_refresh_rotates_after_stage_no_overwrite(self):
        self.assertEqual(self.stage(), "staged_private_local")
        staged_file = self.staged_folder() / "account1.conf"
        original = staged_file.read_bytes()
        self.conf.write_bytes(self.conf.read_bytes().replace(
            b"refresh-one_a", b"new-refresh-one-a"))
        self.assertEqual(self.stage(), "blocked_stale_or_unsafe_stage")
        self.assertEqual(staged_file.read_bytes(), original)

    def test_invalid_crypt_layout_does_not_write(self):
        self.conf.write_bytes(self.conf.read_bytes().replace(
            b"type = crypt", b"type = alias"))
        self.assertEqual(self.stage(), "blocked_layout")
        self.assertFalse(self.parent.exists())

    def test_inconsistent_legacy_services_do_not_write(self):
        name = "rclone_tvshows_1.service"
        path = self.units / name
        path.write_bytes(path.read_bytes().replace(b"--read-only", b"--write"))
        self.assertEqual(self.stage(), "blocked_layout")
        self.assertFalse(self.parent.exists())

    def test_insecure_source_permissions_block(self):
        self.conf.chmod(0o644)
        self.assertEqual(self.stage(), "blocked_local_sources")
        self.assertFalse(self.parent.exists())

    def test_symlink_source_blocks(self):
        alias = Path(self.tmp.name) / "link-conf"
        alias.symlink_to(self.conf)
        self.assertEqual(self.stage(conf_path=str(alias)),
                         "blocked_local_sources")

    def test_existing_target_symlink_never_followed(self):
        self.parent.mkdir(mode=0o700)
        self.staged_folder().symlink_to(self.conf)
        self.assertEqual(self.stage(), "blocked_stale_or_unsafe_stage")
        self.assertEqual(self.conf.read_bytes(), wrapped_conf("crypt"))

    def test_parent_public_permissions_block(self):
        self.parent.mkdir(mode=0o755)
        self.assertEqual(self.stage(), "blocked_private_parent")

    def test_stage_in_wrong_state_does_not_write(self):
        self.state.write_text('{"state": "active", "layout": "two-fuse-v1", '
                              '"schema": 1, '
                              '"candidate_id": "2026-11-17-two-fuse-v1"}')
        self.assertEqual(self.stage(), "blocked_unsafe_mode")
        self.assertFalse(self.parent.exists())

    def test_invalid_state_marker_fails_closed(self):
        self.state.write_text("junk")
        self.assertEqual(self.stage(), "blocked_unsafe_mode")
        self.assertFalse(self.parent.exists())

    def test_changes_before_staging_block(self):
        original = stage._read_sources
        calls = [0]

        def changing(*args):
            calls[0] += 1
            content = original(*args)
            if calls[0] == 2:
                content = (content[0], dict(content[1]), dict(content[2]))
                # Simula escritor que cambia bytes sin cambiar fichero real.
                content[1]["rclone_tvshows_1.service"] += b"\n# changed"
            return content

        with mock.patch.object(stage, "_read_sources",
                               side_effect=changing):
            self.assertEqual(self.stage(), "blocked_source_changed")
        self.assertFalse(self.parent.exists())

    def test_changes_during_write_leave_no_partial_stage(self):
        original = stage._read_sources
        calls = [0]

        def changing(*args):
            calls[0] += 1
            content = original(*args)
            if calls[0] == 3:
                content = (content[0], dict(content[1]), dict(content[2]))
                content[1]["rclone_videos_2.service"] += b"\n# changed"
            return content

        with mock.patch.object(stage, "_read_sources",
                               side_effect=changing):
            self.assertEqual(self.stage(), "blocked_source_changed")
        self.assertFalse(self.staged_folder().exists())
        self.assertEqual(list(self.parent.iterdir()), [])

    def test_published_units_never_escape_private_parent(self):
        self.assertEqual(self.stage(), "staged_private_local")
        for path in self.staged_folder().iterdir():
            self.assertEqual(path.parent, self.staged_folder())
        for root in ("/storage/.config/system.d", "/storage/.mnt/cloud"):
            self.assertFalse(str(self.parent).startswith(root))

    def test_tampered_stage_blocks_without_repairing(self):
        self.assertEqual(self.stage(), "staged_private_local")
        unit = self.staged_folder() / "rclone_library_1.service"
        unit.write_bytes(b"malicious replacement")
        before = unit.read_bytes()
        self.assertEqual(self.stage(), "blocked_stale_or_unsafe_stage")
        self.assertEqual(unit.read_bytes(), before)

    def test_stage_output_returns_no_tokens_or_paths(self):
        result = self.stage()
        self.assertIn(result, ("staged_private_local", "already_staged"))
        for sensitive in ("refresh", "one_a", "rclone.conf", str(self.tmp.name)):
            self.assertNotIn(sensitive, result)

    def test_service_hook_gated_and_runs_after_legacy_phase(self):
        text = (Path(__file__).resolve().parents[1] / "service.py").read_text()
        self.assertIn("RCLONE_TWO_MOUNT_STAGING_ENABLED", text)
        self.assertIn("rclone_two_mount_startup_stage.stage_on_startup", text)
        phase = text[text.index("def _phase1_cloud_storage_blocking"):
                     text.index("# ---------- WRAPPERS ONE-SHOT")]
        self.assertLess(phase.index("start_cloud_storage()"),
                        phase.index("stage_on_startup("))


if __name__ == "__main__":
    unittest.main()
