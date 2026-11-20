# -*- coding: utf-8 -*-
"""A MASTER may exercise CLIENT OAuth ONLY under the explicit dev flag."""
import unittest
from unittest import mock
from lib import rclone_two_mount_client_role as role
from lib import rclone_two_mount_client_apply as apply
from lib import rclone_two_mount_client_worker as worker
from lib import rclone_two_mount_client_early_boot as early


class ScopedRoleTests(unittest.TestCase):
    def test_default_master_still_denied(self):
        with mock.patch.object(role.constants,
                               "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
                               False):
            self.assertFalse(role.allowed("MASTER"))
            self.assertTrue(role.allowed("CLIENT"))
            self.assertFalse(role.allowed("unknown"))
            self.assertEqual(role.label("MASTER"), "BLOCKED")

    def test_dev_master_client_only(self):
        with mock.patch.object(role.constants,
                               "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
                               True):
            self.assertTrue(role.allowed("MASTER"))
            self.assertEqual(role.label("MASTER"),
                             "DEV_MASTER_AS_CLIENT_OAUTH_ONLY")
            self.assertFalse(role.allowed("unknown"))

    def test_no_dev_role_alone_authorizes_live_operations(self):
        with mock.patch.object(role.constants,
                               "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER",
                               True):
            self.assertEqual(worker.tick(lambda x: "", role="MASTER"),
                             "BLOCKED_NOT_AUTHORIZED")
            self.assertEqual(apply.recover_one(
                account_index=0, auth_status="auth",
                read_sources=None, head=None, get=None, probe=None,
                key=None, rpc_call=None, media_check=None),
                "BLOCKED_NOT_AUTHORIZED")
            self.assertEqual(early.execute(), "BLOCKED_NOT_AUTHORIZED")


if __name__ == "__main__":
    unittest.main()
