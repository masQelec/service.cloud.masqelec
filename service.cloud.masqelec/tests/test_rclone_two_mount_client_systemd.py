# -*- coding: utf-8 -*-
"""No real systemd calls: account-isolated mount and ordering regressions."""
import unittest
from lib import rclone_two_mount_client_systemd as systemd
from lib import rclone_two_mount_plan as plan


def mountinfo(account, *, root=True, binds=True, stacked=False):
    base = plan.FUSE_ROOTS[account]
    paths = [(base, "/", 501)]
    if binds:
        paths += [(dest, "/" + folder, 501) for _, i, folder, dest
                  in plan.BIND_MAP if i == account]
    if not root:
        paths = [row for row in paths if row[0] != base]
    if stacked and paths:
        paths.append(paths[-1])
    return "".join("{} 1 0:75 {} {} rw - fuse.rclone drive{} rw\n".format(
        20 + ix, fsroot, target, account) for ix, (target, fsroot, _) in
        enumerate(paths))


class SystemdTests(unittest.TestCase):
    def setUp(self):
        self.actions = []
        self.mounts = mountinfo(0)
        self.active = True
        self.writer = False
        self.media = True

    def run(self, args):
        self.actions.append(tuple(args))
        if args[1] == "is-active":
            return self.active
        return True

    def adapter(self, **kwargs):
        return systemd.AccountSystemd(
            0, enabled=True, run=self.run,
            mountinfo=lambda: self.mounts,
            writer_present=lambda _: self.writer,
            media_check=lambda _: self.media,
            wait=lambda _: None, retries=2, **kwargs)

    def test_only_account_zero_units(self):
        a = self.adapter()
        self.assertTrue(a.stop(0))
        self.assertEqual([x[-1] for x in self.actions],
                         [a.bind_units[1], a.bind_units[0], a.root_unit])
        self.assertNotIn(plan.ACCOUNT_UNITS[1],
                         [x[-1] for x in self.actions])

    def test_root_before_bind_start(self):
        a = self.adapter()
        self.assertTrue(a.start(0))
        self.assertEqual([x[-1] for x in self.actions],
                         [a.root_unit, a.bind_units[0], a.bind_units[1]])

    def test_no_root_no_binds(self):
        self.mounts = ""
        a = self.adapter()
        self.assertFalse(a.start(0))
        self.assertEqual(len(self.actions), 1)

    def test_mounts_writer_or_active_block_quiescence(self):
        a = self.adapter()
        self.assertFalse(a.quiescent(0))
        self.mounts = ""
        self.assertFalse(a.quiescent(0))
        self.active = False
        self.writer = True
        self.assertFalse(a.quiescent(0))
        self.writer = False
        self.assertTrue(a.quiescent(0))

    def test_valid_health_requires_media(self):
        a = self.adapter()
        self.assertTrue(a.healthy(0))
        self.media = False
        self.assertFalse(a.healthy(0))

    def test_rejects_stacked_or_incomplete(self):
        a = self.adapter()
        self.mounts = mountinfo(0, stacked=True)
        self.assertFalse(a.healthy(0))
        self.mounts = mountinfo(0, binds=False)
        self.assertFalse(a.healthy(0))

    def test_rejects_wrong_account_and_disabled(self):
        a = self.adapter()
        with self.assertRaises(PermissionError):
            a.stop(1)
        b = systemd.AccountSystemd(0, enabled=False, run=self.run)
        with self.assertRaises(PermissionError):
            b.start(0)
        self.assertEqual(self.actions, [])

    def test_mismatched_index_type(self):
        for value in (True, -1, 2, "0"):
            with self.assertRaises(ValueError):
                systemd.account_units(value)

    def test_no_media_callback_health_fails(self):
        a = systemd.AccountSystemd(
            0, enabled=True, run=self.run, mountinfo=lambda: self.mounts)
        self.assertFalse(a.healthy(0))

    def test_writer_probe_unknown_is_busy(self):
        # A callback that cannot prove quiescence must never return True.
        self.mounts = ""
        self.active = False
        a = self.adapter()
        self.writer = True
        self.assertFalse(a.quiescent(0))


if __name__ == "__main__":
    unittest.main()
