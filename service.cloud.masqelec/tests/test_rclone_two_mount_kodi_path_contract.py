# -*- coding: utf-8 -*-
"""Contrato de rutas Kodi al generar 2 FUSE + 4 bind (sin IO real)."""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_plan as plan
from lib import rclone_mount_isolation as isolation
from test_rclone_mount_isolation import sample_units, wrapped_conf


EXPECTED = {
    "masqelec_bind_tvshows_1.service": (
        "/storage/.mnt/cloud/1/tvshows", "/storage/.mnt/tvshows/1"),
    "masqelec_bind_tvshows_2.service": (
        "/storage/.mnt/cloud/2/tvshows", "/storage/.mnt/tvshows/2"),
    "masqelec_bind_videos_1.service": (
        "/storage/.mnt/cloud/1/movies", "/storage/.mnt/videos/1"),
    "masqelec_bind_videos_2.service": (
        "/storage/.mnt/cloud/2/movies", "/storage/.mnt/videos/2"),
}


def exec_lines(raw, directive):
    text = raw.decode("utf-8", "strict")
    return [line[len(directive) + 1:] for line in text.splitlines()
            if line.startswith(directive + "=")]


class KodiPathContractTests(unittest.TestCase):
    def setUp(self):
        self.artifacts = plan.generate(wrapped_conf("crypt"), sample_units())

    def test_legacy_targets_and_bind_destinations_are_identical(self):
        legacy = {target for _, _, _, target in isolation.MOUNT_SPECS}
        targets = {destination for _, destination in EXPECTED.values()}
        self.assertEqual(legacy, targets)
        self.assertEqual(len(legacy), 4)
        self.assertEqual({name for name, *_ in plan.BIND_MAP}, set(EXPECTED))

    def test_generated_binds_have_exact_source_and_destination(self):
        for unit, (source, destination) in EXPECTED.items():
            with self.subTest(unit=unit):
                raw, mode = self.artifacts[unit]
                self.assertEqual(mode, 0o644)
                self.assertEqual(
                    exec_lines(raw, "ExecStart"),
                    ["/bin/mount --bind " + source + " " + destination])
                self.assertEqual(exec_lines(raw, "ExecStop"),
                                 ["/bin/umount " + destination])
                self.assertIn(
                    "/bin/sh -c '! /bin/mountpoint -q " + destination + "'",
                    exec_lines(raw, "ExecStartPre"))

    def test_generated_root_mounts_do_not_take_over_legacy_destinations(self):
        for index in (1, 2):
            with self.subTest(account=index):
                unit = "rclone_library_%d.service" % index
                raw, mode = self.artifacts[unit]
                self.assertEqual(mode, 0o644)
                starts = exec_lines(raw, "ExecStart")
                self.assertEqual(len(starts), 1)
                self.assertIn(
                    "/storage/.mnt/cloud/%d" % index, starts[0])
                self.assertIn(
                    "users_library_%d:" % index, starts[0])
                for _, destination in EXPECTED.values():
                    self.assertNotIn(
                        " " + destination + " ", " " + starts[0] + " ")

    def test_exactly_six_units_and_two_private_account_configs(self):
        units = {name for name in self.artifacts
                 if name.endswith(".service")}
        self.assertEqual(units, set(EXPECTED) | {
            "rclone_library_1.service", "rclone_library_2.service"})
        for index in (1, 2):
            data, mode = self.artifacts["account%d.conf" % index]
            self.assertEqual(mode, 0o600)
            self.assertTrue(data)

    def test_generation_has_no_strm_outputs(self):
        self.assertFalse(any(name.endswith(".strm")
                             for name in self.artifacts))


if __name__ == "__main__":
    unittest.main()
