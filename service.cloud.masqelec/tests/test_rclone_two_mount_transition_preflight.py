# -*- coding: utf-8 -*-
"""Transición: preflight standalone sin alterar servicios ni leer OneDrive."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import types
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
from test_rclone_mount_isolation import wrapped_conf, sample_units

script = HERE / "tools/rclone_two_mount_transition_preflight.py"
spec = importlib.util.spec_from_file_location("transition_gate", script)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


def mountinfo(omit=None, stacked=None):
    rows = []
    for number, (_name, _index, _folder, target) in enumerate(gate.SERVICES):
        if target != omit:
            entry = "30 1 0:{} / {} rw - fuse.rclone library rw".format(
                80+number, target)
            rows.append(entry)
            if target == stacked:
                rows.append(entry)
    return "\n".join(rows)


class TransitionGateTests(unittest.TestCase):
    def setUp(self):
        self.conf = wrapped_conf("crypt")
        self.units = sample_units()
        self.active = {name: True for name, *_ in gate.SERVICES}

    def inspect(self, **changes):
        kw = dict(config=self.conf, units=self.units,
                  mountinfo=mountinfo(), active=self.active,
                  new_units_exist=False, state_absent=True)
        kw.update(changes)
        return gate.evaluate(**kw)

    def test_expected_local_state_passes(self):
        self.assertTrue(all(self.inspect().values()))

    def test_missing_mount_fails(self):
        missing = gate.SERVICES[0][3]
        self.assertFalse(self.inspect(mountinfo=mountinfo(omit=missing))[
            "LEGACY_MOUNTS"])

    def test_stacked_mount_fails(self):
        target = gate.SERVICES[2][3]
        self.assertFalse(self.inspect(mountinfo=mountinfo(stacked=target))[
            "LEGACY_MOUNTS"])

    def test_existing_new_mount_fails(self):
        extra = "90 1 0:6 / /storage/.mnt/cloud/1 rw - fuse.rclone x rw"
        self.assertFalse(self.inspect(mountinfo=mountinfo()+"\n"+extra)[
            "NEW_MOUNTS_ABSENT"])

    def test_missing_old_service_fails(self):
        active = dict(self.active)
        active["rclone_videos_1.service"] = False
        self.assertFalse(self.inspect(active=active)["LEGACY_SERVICES"])

    def test_new_units_installed_fails(self):
        self.assertFalse(self.inspect(new_units_exist=True)[
            "NEW_UNITS_ABSENT"])

    def test_active_marker_fails(self):
        self.assertFalse(self.inspect(state_absent=False)[
            "ROLLOUT_STATE_LEGACY"])

    def test_invalid_crypt_blocks(self):
        broken = self.conf.replace(b"type = crypt", b"type = alias", 1)
        self.assertFalse(self.inspect(config=broken)["CONFIG"])

    def test_missing_refresh_blocks(self):
        broken = self.conf.replace(b"refresh-one_a", b"")
        self.assertFalse(self.inspect(config=broken)["CONFIG"])

    def test_drive_identity_mismatch_blocks(self):
        broken = self.conf.replace(b"drive_type = personal",
                                   b"drive_type = ", 1)
        self.assertFalse(self.inspect(config=broken)["CONFIG"])

    def test_legacy_config_uses_wrong_path_blocks(self):
        units = dict(self.units)
        units["rclone_videos_2.service"] = units[
            "rclone_videos_2.service"].replace(
                b"--config /storage/.config/rclone/rclone.conf",
                b"--config /tmp/wrong")
        self.assertFalse(self.inspect(units=units)["LEGACY_UNITS"])

    def test_legacy_no_readonly_blocks(self):
        units = dict(self.units)
        units["rclone_tvshows_1.service"] = units[
            "rclone_tvshows_1.service"].replace(b"--read-only", b"--write")
        self.assertFalse(self.inspect(units=units)["LEGACY_UNITS"])

    def test_malformed_mountinfo_blocks(self):
        self.assertFalse(self.inspect(mountinfo="broken")["LEGACY_MOUNTS"])

    def test_cli_only_preflight_accepted(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gate.main(["--apply"]), 2)
        self.assertIn("BLOCKED_INVALID_MODE", out.getvalue())

    def test_cli_does_not_echo_tokens(self):
        with mock.patch.object(gate, "_read_regular",
                               side_effect=OSError("secret-token-here")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gate.main(["--preflight"]), 2)
        self.assertNotIn("secret-token-here", out.getvalue())
        self.assertIn("CUTOVER_AUTHORIZED=NO", out.getvalue())

    def test_cli_good_inputs_only_read_and_check_status(self):
        by_path = {gate.CANONICAL: self.conf}
        by_path.update({
            os.path.join(gate.SYSTEMD, name): content
            for name, content in self.units.items()
        })
        class File:
            def __enter__(self): return io.StringIO(mountinfo())
            def __exit__(self, *args): pass
        with mock.patch.object(gate, "_read_regular",
                               side_effect=lambda path, **_: by_path[path]), \
             mock.patch.object(gate, "_active", return_value=True), \
             mock.patch.object(gate.os.path, "lexists", return_value=False), \
             mock.patch("builtins.open", return_value=File()), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            code = gate.main(["--preflight"])
        self.assertEqual(code, 0)
        self.assertIn("PREFLIGHT_RESULT=PASS_READ_ONLY", out.getvalue())


if __name__ == "__main__":
    unittest.main()
