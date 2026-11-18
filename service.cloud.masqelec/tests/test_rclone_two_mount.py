# -*- coding: utf-8 -*-
"""Pruebas sin systemctl para preparar 2 FUSE + 4 bind en clientes."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_health as health
from lib import rclone_token_policy as policy
from test_rclone_mount_isolation import wrapped_conf, sample_units


def mountinfo(valid=True, swapped=False):
    rows = []
    for i in (0, 1):
        device = "0:{}".format(i + 45)
        source = "users_library_{}:".format(i+1)
        root = plan.FUSE_ROOTS[i]
        rows.append(
            "{} 1 {} / {} rw - fuse.rclone {} rw".format(
                i+100, device, root, source
            )
        )
        for j, (_, owner, folder, target) in enumerate(plan.BIND_MAP):
            if i != owner:
                continue
            subroot = "/" + folder
            if swapped and folder == "movies":
                subroot = "/tvshows"
            rows.append(
                "{} 1 {} {} {} rw - fuse.rclone {} rw".format(
                    200+i*10+j, device if valid else "0:222", subroot,
                    target, source
                )
            )
    return "\n".join(rows)


class TwoMountPlanTests(unittest.TestCase):
    def setUp(self):
        self.conf = wrapped_conf("crypt")
        self.units = sample_units()
        # Ensayar también parámetros de rendimiento presentes en unidades reales.
        self.units = {
            name: content.replace(
                b"--buffer-size 16M\n",
                b"--buffer-size 16M --vfs-cache-mode off\n",
            )
            for name, content in self.units.items()
        }

    def test_two_configs_each_crypt_and_one_onedrive(self):
        for index in (0, 1):
            content = plan.account_snapshot(self.conf, index)
            self.assertEqual(len(policy.sections(content)), 2)
            self.assertEqual(len(policy.oauth_tokens(content)), 1)
            self.assertEqual(
                policy.sections(content)[plan.ACCOUNT_REMOTES[index]]
                ["filename_encryption"], "off")
            self.assertNotIn(b"[updater]", content)
            self.assertNotIn(b"[logs]", content)

    def test_same_kodi_paths_and_only_two_rclone_root_units(self):
        bundle = plan.generate(self.conf, self.units)
        self.assertEqual(len(bundle), 8)
        self.assertEqual({x[-1] for x in plan.BIND_MAP}, {
            "/storage/.mnt/videos/1", "/storage/.mnt/videos/2",
            "/storage/.mnt/tvshows/1", "/storage/.mnt/tvshows/2",
        })
        self.assertEqual(set(plan.ACCOUNT_UNITS), set(
            name for name in bundle if name.startswith("rclone_")
        ))

    def test_root_unit_keeps_original_rclone_performance_flags(self):
        bundle = plan.generate(self.conf, self.units)
        for index, unit in enumerate(plan.ACCOUNT_UNITS):
            text = bundle[unit][0].decode()
            # El rclone original de KodiELEC funciona con Type=simple.
            # No introducir dependencia de sd_notify sin probarla.
            self.assertIn("Type=simple", text)
            self.assertNotIn("Type=notify", text)
            self.assertNotIn("NotifyAccess=", text)
            self.assertIn("--read-only", text)
            self.assertIn("users_library_{}:".format(index+1), text)
            self.assertIn(plan.ACCOUNT_CONFS[index], text)
            self.assertIn("--buffer-size", text)
            self.assertIn("--vfs-cache-mode", text)
            # El ensayo real systemd usó /bin/umount sin depender de
            # /bin/fusermount; conservar el binario comprobado en KodiELEC.
            self.assertIn("ExecStop=/bin/umount " + plan.FUSE_ROOTS[index],
                          text)
            self.assertNotIn("ExecStop=/bin/fusermount", text)
            self.assertNotIn("--config /storage/.config/rclone/rclone.conf",
                             text)
            self.assertNotIn("ExecStop=/bin/fusermount -uz /storage/.mnt/tvshows/",
                             text)

    def test_root_units_validate_legacy_flags_for_each_account(self):
        units = dict(self.units)
        units["rclone_videos_1.service"] = units[
            "rclone_videos_1.service"].replace(
                b"--buffer-size 16M", b"--buffer-size 32M"
            )
        with self.assertRaisesRegex(ValueError, "Opciones"):
            plan.generate(self.conf, units)

    def test_bind_units_have_dependencies_and_never_unmount_legacy_prestart(self):
        bundle = plan.generate(self.conf, self.units)
        for name, index, folder, target in plan.BIND_MAP:
            unit = bundle[name][0].decode()
            self.assertIn("BindsTo=" + plan.ACCOUNT_UNITS[index], unit)
            self.assertIn("After=" + plan.ACCOUNT_UNITS[index], unit)
            self.assertIn(plan.FUSE_ROOTS[index] + "/" + folder, unit)
            self.assertIn(target, unit)
            self.assertIn("mount --bind", unit)
            self.assertIn("mountpoint -q " + target, unit)
            self.assertNotIn("ExecStartPre=/bin/umount", unit)


    def test_binds_wait_bounded_for_real_fuse_ready_with_type_simple(self):
        bundle = plan.generate(self.conf, self.units)
        for name, i, folder, target in plan.BIND_MAP:
            unit = bundle[name][0].decode("utf-8")
            self.assertIn("TimeoutStartSec=45", unit)
            self.assertIn("Type=oneshot", unit)
            self.assertIn("BindsTo=" + plan.ACCOUNT_UNITS[i], unit)
            self.assertIn("After=" + plan.ACCOUNT_UNITS[i], unit)
            self.assertIn("/bin/mountpoint -q " + plan.FUSE_ROOTS[i], unit)
            self.assertIn("[ -d " + plan.FUSE_ROOTS[i]
                          + "/" + folder + " ]", unit)
            self.assertNotIn("/bin/test", unit)
            self.assertIn("/bin/sleep 1", unit)
            self.assertIn("done; exit 1", unit)
            self.assertIn("ExecStart=/bin/mount --bind", unit)
            self.assertNotIn("rclone lsf", unit)
            self.assertNotIn("Type=notify", unit)

    def test_bind_checks_are_busybox_shell_builtin_not_bin_test(self):
        bundle = plan.generate(self.conf, self.units)
        for name, index, folder, _ in plan.BIND_MAP:
            unit = bundle[name][0].decode("utf-8")
            self.assertNotIn("/bin/test", unit)
            self.assertIn(
                "[ -d " + plan.FUSE_ROOTS[index] + "/" + folder + " ]",
                unit)
            self.assertIn("/bin/sh -c", unit)

    def test_bind_rejects_busy_kodi_target_before_waiting(self):
        bundle = plan.generate(self.conf, self.units)
        for name, _, _, target in plan.BIND_MAP:
            unit = bundle[name][0].decode("utf-8")
            busy = "ExecStartPre=/bin/sh -c '! /bin/mountpoint -q " + target + "'"
            self.assertIn(busy, unit)
            self.assertLess(unit.index(busy), unit.index("for retry in"))

    def test_manifest_public_does_not_embed_oauth_or_crypt(self):
        bundle = plan.generate(self.conf, self.units)
        manifest = plan.public_manifest(bundle)
        raw = json.dumps(manifest)
        self.assertEqual(len(manifest["unit_sha256"]), 6)
        self.assertTrue(rollout.version_supported(manifest))
        self.assertNotIn("refresh", raw)
        self.assertNotIn("password", raw)
        self.assertNotIn("OBFUSCATED_TEST", raw)
        self.assertEqual(manifest["activation"], "operator_only")

    def test_stage_creates_private_credentials_and_never_writes_live(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as root:
            os.chmod(root, 0o700)
            manifest = plan.stage_to_tmp(root, self.conf, self.units)
            self.assertEqual(len(os.listdir(root)), 9)
            for path in os.listdir(root):
                mode = os.stat(os.path.join(root, path)).st_mode & 0o777
                self.assertEqual(mode, 0o600 if path.endswith(
                    ".conf") or path == "rollout-manifest.json" else 0o644)
            with open(os.path.join(root, "rollout-manifest.json")) as stream:
                self.assertEqual(json.load(stream), manifest)

    def test_stage_rejects_nonempty_or_insecure_directories(self):
        with tempfile.TemporaryDirectory(dir="/tmp") as root:
            os.chmod(root, 0o700)
            with open(os.path.join(root, "exists"), "w") as out:
                out.write("x")
            with self.assertRaisesRegex(ValueError, "seguro"):
                plan.stage_to_tmp(root, self.conf, self.units)
            os.unlink(os.path.join(root, "exists"))
            os.chmod(root, 0o755)
            with self.assertRaisesRegex(ValueError, "seguro"):
                plan.stage_to_tmp(root, self.conf, self.units)

    def test_wrong_crypt_identity_blocks_plan(self):
        bad = self.conf.replace(b"type = crypt", b"type = alias", 1)
        with self.assertRaisesRegex(ValueError, "crypt"):
            plan.generate(bad, self.units)

    def test_wrong_dependency_count_blocks_plan(self):
        bad = self.conf.replace(
            b"remote = one_a:library", b"remote = updater:library", 1)
        with self.assertRaisesRegex(ValueError, "OneDrive"):
            plan.generate(bad, self.units)


class TwoMountRolloutTests(unittest.TestCase):
    def test_disabled_feature_blocks_previously_activated_client(self):
        with tempfile.TemporaryDirectory() as root:
            marker = os.path.join(root, "state.json")
            with open(marker, "w") as out:
                out.write('{"schema":1,"layout":"two-fuse-v1","state":"active","candidate_id":"2026-11-17-two-fuse-v1"}')
            self.assertEqual(rollout.mode(False, marker), "unsafe")

    def test_disabled_feature_keeps_prepared_client_legacy(self):
        with tempfile.TemporaryDirectory() as root:
            marker = os.path.join(root, "state.json")
            with open(marker, "w") as out:
                out.write('{"schema":1,"layout":"two-fuse-v1","state":"prepared","candidate_id":"2026-11-17-two-fuse-v1"}')
            self.assertEqual(rollout.mode(False, marker), "legacy")

    def test_no_marker_defaults_to_legacy(self):
        self.assertEqual(rollout.mode(True, "/tmp/nonexistent-masqelec-state-1234"),
                         "legacy")

    def test_prepared_client_remains_legacy_under_updater(self):
        with tempfile.TemporaryDirectory() as root:
            marker = os.path.join(root, "state.json")
            with open(marker, "w") as out:
                out.write('{"schema":1,"layout":"two-fuse-v1","state":"prepared","candidate_id":"2026-11-17-two-fuse-v1"}')
            self.assertEqual(rollout.mode(True, marker), "prepared")
            self.assertEqual(rollout.managed_legacy_services("prepared"),
                             rollout.LEGACY_SERVICES)
            self.assertEqual(rollout.apply_permission("prepared"), "stage_only")

    def test_active_client_never_downloads_legacy_units(self):
        with tempfile.TemporaryDirectory() as root:
            marker = os.path.join(root, "state.json")
            with open(marker, "w") as out:
                out.write('{"schema":1,"layout":"two-fuse-v1","state":"active","candidate_id":"2026-11-17-two-fuse-v1"}')
            self.assertEqual(rollout.mode(True, marker), "active")
            self.assertEqual(rollout.managed_legacy_services("active"), ())
            self.assertEqual(rollout.apply_permission("active"),
                             "already_active_do_not_restart")

    def test_invalid_marker_fails_closed(self):
        for invalid in (b"{}", b"{", b"[]",
                        b'{"schema":true,"layout":"two-fuse-v1","state":"active"}',
                        b'{"schema":1,"layout":"new","state":"active"}'):
            with tempfile.TemporaryDirectory() as root:
                marker = os.path.join(root, "state.json")
                with open(marker, "wb") as out:
                    out.write(invalid)
                self.assertEqual(rollout.mode(True, marker), "unsafe")
                with self.assertRaises(ValueError):
                    rollout.managed_legacy_services("unsafe")

    def test_wrong_client_candidate_version_is_blocked(self):
        with tempfile.TemporaryDirectory() as root:
            marker = os.path.join(root, "state.json")
            with open(marker, "w") as out:
                out.write('{"schema":1,"layout":"two-fuse-v1","state":"active",'
                          '"candidate_id":"some-future-pilot"}')
            self.assertEqual(rollout.mode(True, marker), "unsafe")

    def test_symlink_marker_is_unsafe(self):
        with tempfile.TemporaryDirectory() as root:
            real = os.path.join(root, "state-real")
            with open(real, "w") as out:
                out.write('{"schema":1,"layout":"two-fuse-v1","state":"active","candidate_id":"2026-11-17-two-fuse-v1"}')
            link = os.path.join(root, "state-link")
            os.symlink(real, link)
            self.assertEqual(rollout.mode(True, link), "unsafe")


class TwoMountHealthTests(unittest.TestCase):
    def test_two_fuse_four_bind_passes(self):
        self.assertTrue(health.check_two_fuse_four_bind(mountinfo()))

    def test_missing_bind_fails(self):
        raw = mountinfo()
        raw = "\n".join(line for line in raw.splitlines()
                        if "/storage/.mnt/videos/2" not in line)
        self.assertFalse(health.check_two_fuse_four_bind(raw))

    def test_wrong_source_device_fails(self):
        self.assertFalse(health.check_two_fuse_four_bind(
            mountinfo(valid=False)))

    def test_swapped_movies_series_fails(self):
        self.assertFalse(health.check_two_fuse_four_bind(
            mountinfo(swapped=True)))

    def test_missing_root_fuse_fails(self):
        raw = mountinfo().replace("fuse.rclone", "tmpfs", 1)
        self.assertFalse(health.check_two_fuse_four_bind(raw))

    def test_mountinfo_truncated_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "separador"):
            health.check_two_fuse_four_bind("bad")
