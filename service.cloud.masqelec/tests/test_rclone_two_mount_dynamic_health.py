# -*- coding: utf-8 -*-
"""Validador mountinfo parametrizado: no usa FUSE real."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_health as health


def synthetic_mountinfo(*, wrong_subpath=False, wrong_device=False,
                        omit_last=False):
    lines = []
    roots = ("/tmp/lab/fuse/1", "/tmp/lab/fuse/2")
    binds = (
        (0, "movies", "/tmp/lab/bind/videos/1"),
        (1, "movies", "/tmp/lab/bind/videos/2"),
        (0, "tvshows", "/tmp/lab/bind/tvshows/1"),
        (1, "tvshows", "/tmp/lab/bind/tvshows/2"),
    )
    for idx, root in enumerate(roots):
        device = "0:" + str(80 + idx)
        src = "lab" + str(idx + 1) + ":"
        lines.append(
            "100 1 %s / %s rw - fuse.rclone %s rw" % (
                device, root, src))
        for k, (a, folder, target) in enumerate(binds):
            if a != idx or (omit_last and k == 3):
                continue
            child_root = ("/wrong" if wrong_subpath and k == 0
                          else "/" + folder)
            child_dev = "0:99" if wrong_device and k == 0 else device
            lines.append(
                "101 1 %s %s %s rw - fuse.rclone %s rw" % (
                    child_dev, child_root, target, src))
    return "\n".join(lines), roots, tuple(
        (a, folder, target) for a, folder, target in binds)


class DynamicHealthTests(unittest.TestCase):
    def test_alternate_root_and_binds_pass(self):
        data, roots, binds = synthetic_mountinfo()
        self.assertTrue(health.check_layout_at(data, roots, binds))

    def test_missing_bind_fails(self):
        data, roots, binds = synthetic_mountinfo(omit_last=True)
        self.assertFalse(health.check_layout_at(data, roots, binds))

    def test_wrong_subpath_fails(self):
        data, roots, binds = synthetic_mountinfo(wrong_subpath=True)
        self.assertFalse(health.check_layout_at(data, roots, binds))

    def test_wrong_device_fails(self):
        data, roots, binds = synthetic_mountinfo(wrong_device=True)
        self.assertFalse(health.check_layout_at(data, roots, binds))

    def test_invalid_mountinfo_fails_closed(self):
        _, roots, binds = synthetic_mountinfo()
        self.assertFalse(health.check_layout_at("broken", roots, binds))

    def test_mismatch_bind_count_fails(self):
        data, roots, binds = synthetic_mountinfo()
        self.assertFalse(health.check_layout_at(data, roots, binds[:3]))

    def test_duplicate_target_fails(self):
        data, roots, binds = synthetic_mountinfo()
        broken = binds[:3] + ((1, "tvshows", binds[0][2]),)
        self.assertFalse(health.check_layout_at(data, roots, broken))

    def test_unsupported_folder_fails(self):
        data, roots, binds = synthetic_mountinfo()
        broken = ((0, "scripts", binds[0][2]),) + binds[1:]
        self.assertFalse(health.check_layout_at(data, roots, broken))

    def test_bool_account_index_fails(self):
        data, roots, binds = synthetic_mountinfo()
        broken = ((True, "movies", binds[0][2]),) + binds[1:]
        self.assertFalse(health.check_layout_at(data, roots, broken))

    def test_missing_fuse_root_fails(self):
        data, roots, binds = synthetic_mountinfo()
        self.assertFalse(health.check_layout_at(
            data, (roots[0], "/tmp/absent"), binds))


if __name__ == "__main__":
    unittest.main()
