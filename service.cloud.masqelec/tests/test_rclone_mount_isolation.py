# -*- coding: utf-8 -*-
"""Laboratorio unitario de aislamiento de 4 rclone mount sin Kodi ni red."""
import json
import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from lib import rclone_mount_isolation as iso
from lib import rclone_token_policy as policy


def sample_conf():
    data = []
    for name, kind in (("users_library_1", "onedrive"),
                       ("users_library_2", "onedrive"),
                       ("updater", "drive"), ("logs", "drive")):
        entry = ["[" + name + "]", "type = " + kind,
                 "client_id = isolated-demo"]
        if kind == "onedrive":
            entry += ["drive_id = " + name + "-id",
                      "drive_type = personal"]
        entry.append("token = " + json.dumps({
            "access_token": "access-" + name,
            "refresh_token": "refresh-" + name,
            "expiry": "2026-11-17T09:00:00Z",
        }))
        data.extend(entry + [""])
    data.extend(["[alias]", "type = alias", "remote = users_library_1:", "",
                 "[crypt]", "type = crypt",
                 "remote = users_library_2:secret", "password = opaque", ""])
    return "\n".join(data).encode("utf-8")


def sample_units():
    result = {}
    for service, remote, folder, mountpoint in iso.MOUNT_SPECS:
        result[service] = (
            "[Unit]\nDescription=LAB\n[Service]\n"
            "ExecStart=/storage/.config/rclone/rclone mount "
            + remote + ":" + folder + " " + mountpoint +
            " \\\n  --config /storage/.config/rclone/rclone.conf \\\n"
            "  --read-only \\\n  --buffer-size 16M\n"
        ).encode("utf-8")
    return result


def wrapped_conf(kind="alias"):
    """4 OAuth + 2 remotos virtuales usados por las unidades systemd."""
    raw = sample_conf().split(b"[alias]\n")[0]
    raw = raw.replace(b"[users_library_1]", b"[one_a]")
    raw = raw.replace(b"[users_library_2]", b"[one_b]")
    if kind in ("alias", "crypt", "chunker"):
        suffix = (
            "[users_library_1]\ntype = {kind}\nremote = one_a:library\n"
            "{options}\n"
            "[users_library_2]\ntype = {kind}\nremote = one_b:library\n"
            "{options}"
        ).format(
            kind=kind,
            options=("filename_encryption = off\n"
                     "directory_name_encryption = false\n"
                     "password = OBFUSCATED_TEST_VALUE\n"
                     "password2 = OBFUSCATED_TEST_SALT\n")
                    if kind == "crypt" else "",
        )
    elif kind == "combine":
        suffix = (
            "[users_library_1]\ntype = combine\n"
            "upstreams = first=one_a:files second=updater:share\n\n"
            "[users_library_2]\ntype = combine\n"
            "upstreams = first=one_b:files second=logs:share\n"
        )
    elif kind == "union":
        suffix = (
            "[users_library_1]\ntype = union\n"
            "upstreams = one_a:files:ro updater:share:ro\n\n"
            "[users_library_2]\ntype = union\n"
            "upstreams = one_b:files:ro logs:share:ro\n"
        )
    else:
        raise ValueError("Tipo de fixture desconocido")
    return raw + suffix.encode("utf-8")



class MountIsolationTests(unittest.TestCase):
    def setUp(self):
        self.config = sample_conf()
        self.units = sample_units()

    def test_layout_exact_two_accounts_four_services(self):
        self.assertEqual(len(iso.MOUNT_SPECS), 4)
        self.assertEqual([r for _, r, _, _ in iso.MOUNT_SPECS].count("users_library_1"), 2)
        self.assertEqual([r for _, r, _, _ in iso.MOUNT_SPECS].count("users_library_2"), 2)
        self.assertTrue(iso.inspect_units(self.units))

    def test_one_process_one_remote_and_no_google_tokens(self):
        for _, remote, _, _ in iso.MOUNT_SPECS:
            raw = iso.select_remote(self.config, remote)
            self.assertEqual(list(policy.oauth_tokens(raw)), [remote])
            self.assertNotIn(b"[updater]", raw)
            self.assertNotIn(b"[logs]", raw)
            self.assertNotIn(b"[crypt]", raw)
            self.assertNotIn(b"[alias]", raw)

    def test_one_account_same_token_in_two_initial_snapshots(self):
        snapshots = {service: iso.select_remote(self.config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        self.assertEqual(iso.account_divergence(snapshots),
                         {"users_library_1": "consistent",
                          "users_library_2": "consistent"})

    def test_divergent_refresh_tokens_not_silently_merged(self):
        snapshots = {service: iso.select_remote(self.config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        snapshots["rclone_videos_1.service"] = snapshots[
            "rclone_videos_1.service"].replace(b"refresh-users_library_1",
                                                b"other-refresh")
        status = iso.account_divergence(snapshots)
        self.assertEqual(status["users_library_1"], "diverged")
        self.assertEqual(status["users_library_2"], "consistent")

    def test_changed_onedrive_identity_blocks_reconciliation(self):
        snapshots = {service: iso.select_remote(self.config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        snapshots["rclone_videos_2.service"] = snapshots[
            "rclone_videos_2.service"].replace(b"drive_type = personal",
                                                b"drive_type = business")
        with self.assertRaisesRegex(ValueError, "Identidad"):
            iso.account_divergence(snapshots)

    def test_unit_proposals_contain_unique_paths(self):
        paths = []
        for unit, _remote, _folder, _mount in iso.MOUNT_SPECS:
            proposed = iso.propose_unit(unit, self.units[unit])
            args = iso._start_args(proposed)
            new_path = iso.proposed_config_path(unit)
            paths.append(new_path)
            self.assertEqual(iso._config_arg(args), new_path)
            self.assertIn(b"--read-only", proposed)
            self.assertNotIn(b"--config /storage/.config/rclone/rclone.conf",
                             proposed)
        self.assertEqual(len(set(paths)), 4)

    def test_plan_rejects_unexpected_mount_remote(self):
        units = dict(self.units)
        units["rclone_videos_2.service"] = units[
            "rclone_videos_2.service"].replace(b"users_library_2:movies",
                                                b"users_library_1:movies")
        with self.assertRaisesRegex(ValueError, "Destino o fuente"):
            iso.inspect_units(units)

    def test_plan_rejects_unknown_service_and_modified_config_path(self):
        with self.assertRaises(ValueError):
            iso.proposed_config_path("unknown.service")
        units = dict(self.units)
        units["rclone_videos_1.service"] = units[
            "rclone_videos_1.service"].replace(
                b"--config /storage/.config/rclone/rclone.conf",
                b"--config /tmp/wrong.conf")
        with self.assertRaisesRegex(ValueError, "configuración inesperada"):
            iso.inspect_units(units)

    def test_stage_proposals_only_in_private_temporary_directory(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o700)
            self.assertEqual(iso.stage_in_directory(root, self.config, self.units), 4)
            self.assertEqual(len(os.listdir(root)), 8)
            for filename in os.listdir(root):
                path = os.path.join(root, filename)
                self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "vacío"):
                iso.stage_in_directory(root, self.config, self.units)

    def test_stage_rejects_insecure_or_outside_directory(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o755)
            with self.assertRaisesRegex(ValueError, "0700"):
                iso.stage_in_directory(root, self.config, self.units)

    def test_select_remote_rejects_missing_token(self):
        broken = self.config.replace(b"refresh-users_library_1", b"")
        with self.assertRaises(ValueError):
            iso.select_remote(broken, "users_library_1")

    def test_stage_keeps_original_config_and_units_unmodified(self):
        original = bytes(self.config)
        old_units = dict(self.units)
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o700)
            iso.stage_in_directory(root, self.config, self.units)
        self.assertEqual(self.config, original)
        self.assertEqual(self.units, old_units)


    def test_stage_accepts_tmp_symlink_target_inside_real_temp_tree(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o700)
            actual_realpath = iso.os.path.realpath
            def redirected(path):
                if path == "/tmp":
                    return "/var/tmpfs"
                if path == root:
                    return "/var/tmpfs/" + os.path.basename(root)
                return actual_realpath(path)
            with mock.patch.object(iso.os.path, "realpath", side_effect=redirected):
                self.assertEqual(
                    iso.stage_in_directory(root, self.config, self.units), 4
                )

    def test_stage_refuses_tmp_prefix_escape(self):
        with tempfile.TemporaryDirectory(prefix="masqelec-isolation-", dir="/tmp") as root:
            os.chmod(root, 0o700)
            actual_realpath = iso.os.path.realpath
            def redirected(path):
                if path == "/tmp":
                    return "/var/tmpfs"
                if path == root:
                    return "/var/tmpfs-other/escape"
                return actual_realpath(path)
            with mock.patch.object(iso.os.path, "realpath", side_effect=redirected):
                with self.assertRaisesRegex(ValueError, "temporal seguro"):
                    iso.stage_in_directory(root, self.config, self.units)


    def test_wrapper_alias_keeps_exact_dependency_chain(self):
        config = wrapped_conf("alias")
        self.assertEqual(len(policy.sections(config)), 6)
        selected = iso.select_remote(config, "users_library_1")
        self.assertEqual(set(policy.sections(selected)),
                         {"users_library_1", "one_a"})
        self.assertEqual(set(policy.oauth_tokens(selected)), {"one_a"})
        self.assertNotIn(b"[one_b]", selected)
        self.assertNotIn(b"[updater]", selected)

    def test_wrapper_crypt_and_chunker_keeps_backend_options(self):
        for kind in ("crypt", "chunker"):
            config = wrapped_conf(kind)
            selected = iso.select_remote(config, "users_library_2")
            self.assertIn(("type = " + kind).encode(), selected)
            self.assertEqual(
                set(iso.dependency_closure(config, "users_library_2")),
                {"users_library_2", "one_b"}
            )

    def test_combine_root_resolves_two_oauth_upstreams(self):
        config = wrapped_conf("combine")
        part = iso.select_remote(config, "users_library_1")
        self.assertEqual(set(policy.sections(part)),
                         {"users_library_1", "one_a", "updater"})
        self.assertEqual(set(policy.oauth_tokens(part)), {"one_a", "updater"})
        self.assertNotIn(b"[logs]", part)

    def test_union_root_resolves_two_oauth_upstreams(self):
        config = wrapped_conf("union")
        part = iso.select_remote(config, "users_library_2")
        self.assertEqual(set(policy.sections(part)),
                         {"users_library_2", "one_b", "logs"})
        self.assertEqual(set(policy.oauth_tokens(part)), {"one_b", "logs"})

    def test_virtual_roots_stage_four_configs_with_dependencies(self):
        for kind in ("alias", "crypt", "chunker", "combine", "union"):
            config = wrapped_conf(kind)
            with tempfile.TemporaryDirectory(
                    prefix="masqelec-isolation-", dir="/tmp") as root:
                os.chmod(root, 0o700)
                self.assertEqual(
                    iso.stage_in_directory(root, config, self.units), 4)
                for service, remote, _, _ in iso.MOUNT_SPECS:
                    conf_file = os.path.join(
                        root, service.removesuffix(".service") + ".conf")
                    with open(conf_file, "rb") as fd:
                        subset = fd.read()
                    self.assertEqual(
                        set(policy.sections(subset)),
                        set(iso.dependency_closure(config, remote)))
                self.assertEqual(len(os.listdir(root)), 8)

    def test_virtual_roots_account_divergence_without_token_loss(self):
        for kind in ("alias", "crypt", "union", "combine"):
            config = wrapped_conf(kind)
            snapshots = {service: iso.select_remote(config, remote)
                         for service, remote, _, _ in iso.MOUNT_SPECS}
            flags = iso.account_divergence(snapshots)
            self.assertEqual(
                len(flags), 2 if kind in ("alias", "crypt") else 4
            )
            self.assertTrue(all(x == "consistent" for x in flags.values()))

    def test_virtual_roots_divergent_one_account_not_promoted(self):
        config = wrapped_conf("alias")
        snapshots = {service: iso.select_remote(config, remote)
                     for service, remote, _, _ in iso.MOUNT_SPECS}
        snapshots["rclone_videos_1.service"] = snapshots[
            "rclone_videos_1.service"].replace(
                b"refresh-users_library_1", b"different-refresh"
            )
        flags = iso.account_divergence(snapshots)
        self.assertEqual(flags["one_a"], "diverged")
        self.assertEqual(flags["one_b"], "consistent")

    def test_virtual_roots_cycle_rejected(self):
        config = (
            b"[users_library_1]\ntype = alias\nremote = other:\n"
            b"[other]\ntype = alias\nremote = users_library_1:\n"
        )
        with self.assertRaisesRegex(ValueError, "Ciclo"):
            iso.dependency_closure(config, "users_library_1")

    def test_virtual_roots_unknown_backend_rejected(self):
        config = (
            wrapped_conf("alias").replace(
                b"type = alias", b"type = uncommon-wrapper", 1
            )
        )
        with self.assertRaisesRegex(ValueError, "Backend"):
            iso.select_remote(config, "users_library_1")

    def test_virtual_roots_local_paths_rejected(self):
        config = wrapped_conf("alias").replace(
            b"remote = one_a:library", b"remote = /mnt/private"
        )
        with self.assertRaisesRegex(ValueError, "Referencia"):
            iso.select_remote(config, "users_library_1")

    def test_virtual_roots_missing_dependency_rejected(self):
        config = wrapped_conf("alias").replace(
            b"remote = one_a:library", b"remote = missing:library"
        )
        with self.assertRaisesRegex(ValueError, "ausente"):
            iso.select_remote(config, "users_library_1")

    def test_virtual_roots_union_empty_upstreams_rejected(self):
        config = wrapped_conf("union").replace(
            b"upstreams = one_a:files:ro updater:share:ro",
            b"upstreams = "
        )
        with self.assertRaisesRegex(ValueError, "sin upstreams"):
            iso.select_remote(config, "users_library_1")


    def test_crypt_data_encrypted_filenames_plain_preserves_exact_options(self):
        conf = wrapped_conf("crypt")
        for root, upstream in (("users_library_1", "one_a"),
                               ("users_library_2", "one_b")):
            isolated = iso.select_remote(conf, root)
            opts_before = policy.sections(conf)[root]
            opts_after = policy.sections(isolated)[root]
            self.assertEqual(opts_before, opts_after)
            self.assertEqual(opts_after["type"], "crypt")
            self.assertEqual(opts_after["filename_encryption"], "off")
            self.assertEqual(opts_after["directory_name_encryption"], "false")
            self.assertEqual(
                policy.oauth_tokens(isolated)[upstream],
                policy.oauth_tokens(conf)[upstream],
            )
            self.assertEqual(
                set(policy.sections(isolated)), {root, upstream}
            )
            self.assertNotIn(b"[updater]", isolated)
            self.assertNotIn(b"[logs]", isolated)

    def test_crypt_second_account_never_gets_first_password_or_oauth(self):
        config = wrapped_conf("crypt")
        prefix, marker, second = config.partition(b"[users_library_2]")
        self.assertTrue(marker)
        second = second.replace(b"password = OBFUSCATED_TEST_VALUE",
                                b"password = SECOND_VALUE", 1)
        config = prefix + marker + second
        isolated = iso.select_remote(config, "users_library_2")
        self.assertIn(b"password = SECOND_VALUE", isolated)
        self.assertNotIn(b"OBFUSCATED_TEST_VALUE", isolated)
        self.assertNotIn(b"[one_a]", isolated)
        self.assertNotIn(b"[users_library_1]", isolated)

    def test_crypt_missing_underlying_onedrive_blocks_isolation(self):
        conf = wrapped_conf("crypt").replace(
            b"remote = one_a:library", b"remote = missing_remote:library"
        )
        with self.assertRaisesRegex(ValueError, "ausente"):
            iso.select_remote(conf, "users_library_1")



if __name__ == "__main__":
    unittest.main()
