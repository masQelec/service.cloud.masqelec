# -*- coding: utf-8 -*-
"""No necesita Kodi, red, claves ni secretos reales."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_conf_merge as merge


class RcloneConfMergeTests(unittest.TestCase):
    def test_preserve_rotated_local_token_when_static_remote_changed(self):
        local = b'[drive]\ntype = drive\nclient_id = same\ntoken = {"refresh_token":"local-new"}\n'
        remote = b'[drive]\ntype = drive\nclient_id = same\nteam_drive = xyz\ntoken = {"refresh_token":"server-old"}\n'
        # team_drive is part of auth identity => remote wins (intentional).
        out = merge.preserve_local_oauth_tokens(remote, local)
        self.assertIn(b'server-old', out)

    def test_preserve_local_token_for_non_identity_setting(self):
        local = b'[drive]\ntype = drive\nclient_id = same\ntoken = {"refresh_token":"local-new"}\n'
        remote = b'[drive]\ntype = drive\nclient_id = same\nchunk_size = 64M\ntoken = {"refresh_token":"server-old"}\n'
        out = merge.preserve_local_oauth_tokens(remote, local)
        self.assertIn(b'local-new', out)
        self.assertNotIn(b'server-old', out)
        self.assertIn(b'chunk_size = 64M', out)

    def test_other_remote_keeps_remote_token(self):
        local = b'[first]\ntype = drive\ntoken = OLD\n'
        remote = b'[second]\ntype = drive\ntoken = NEW\n'
        out = merge.preserve_local_oauth_tokens(remote, local)
        self.assertIn(b'NEW', out)
        self.assertNotIn(b'OLD', out)

    def test_invalid_repeated_sections_fail_closed(self):
        repeated = b'[drive]\ntype = drive\n[drive]\ntype = drive\n'
        with self.assertRaisesRegex(ValueError, "duplicada"):
            merge.preserve_local_oauth_tokens(repeated, b'')

    def test_diagnostic_never_includes_values_or_tokens(self):
        local = b'[remote_name]\ntype = drive\nclient_secret = SUPERSECRET\ntoken = OLD\n'
        remote = b'[remote_name]\ntype = drive\nclient_secret = NEWSECRET\ntoken = NEW\n'
        diff = merge.compare_non_token_settings(local, remote)
        self.assertEqual(diff, ("client_secret",))
        self.assertNotIn("SUPERSECRET", str(diff))
        self.assertNotIn("NEWSECRET", str(diff))
        self.assertNotIn("OLD", str(diff))

    def test_same_effective_settings_skips_format_only_difference(self):
        local = b'[drive]\ntype=drive\n  token = LOCAL\nchunk_size = 64M\n'
        remote = b'# remote\n[drive]\nchunk_size=64M\ntoken = REMOTE\ntype = drive\n'
        self.assertTrue(merge.same_non_token_settings(local, remote))
        changed = b'[drive]\ntype = drive\nchunk_size = 32M\ntoken = REMOTE\n'
        self.assertFalse(merge.same_non_token_settings(local, changed))



    def test_onedrive_preserve_local_when_same_drive_identity(self):
        local = (b'[library]\ntype = onedrive\ndrive_id = abc\n'
                 b'drive_type = personal\ntoken = LOCAL\n')
        remote = (b'[library]\ntype = onedrive\ndrive_id = abc\n'
                  b'drive_type = personal\ntoken = REMOTE\n')
        out = merge.preserve_local_oauth_tokens(remote, local)
        self.assertIn(b'token = LOCAL', out)
        self.assertNotIn(b'token = REMOTE', out)

    def test_onedrive_changed_drive_id_never_preserves_token(self):
        local = (b'[library]\ntype = onedrive\ndrive_id = first\n'
                 b'drive_type = personal\ntoken = LOCAL\n')
        remote = (b'[library]\ntype = onedrive\ndrive_id = second\n'
                  b'drive_type = personal\ntoken = REMOTE\n')
        out = merge.preserve_local_oauth_tokens(remote, local)
        self.assertIn(b'token = REMOTE', out)
        self.assertNotIn(b'token = LOCAL', out)

    def test_onedrive_changed_drive_type_never_preserves_token(self):
        local = (b'[library]\ntype = onedrive\ndrive_id = same\n'
                 b'drive_type = personal\ntoken = LOCAL\n')
        remote = (b'[library]\ntype = onedrive\ndrive_id = same\n'
                  b'drive_type = business\ntoken = REMOTE\n')
        out = merge.preserve_local_oauth_tokens(remote, local)
        self.assertIn(b'token = REMOTE', out)


    def test_onedrive_startup_identity_guard(self):
        local = (b'[library]\ntype = onedrive\ndrive_id = xyz\n'
                 b'drive_type = personal\ntoken = OLD\n')
        same = local.replace(b'token = OLD', b'token = ROTATED')
        wrong = local.replace(b'drive_id = xyz', b'drive_id = other')
        wrong_type = local.replace(b'drive_type = personal',
                                   b'drive_type = business')
        self.assertFalse(merge.onedrive_identity_changed(same, local))
        self.assertTrue(merge.onedrive_identity_changed(wrong, local))
        self.assertTrue(merge.onedrive_identity_changed(wrong_type, local))

    def test_onedrive_startup_removal_and_addition_are_fenced(self):
        local = b'[library]\ntype = onedrive\ndrive_id = xyz\ntoken = OLD\n'
        other = b'[logs]\ntype = drive\ntoken = LOG\n'
        self.assertTrue(merge.onedrive_identity_changed(other, local))
        self.assertTrue(merge.onedrive_identity_changed(local, other))

    def test_google_drive_change_does_not_trigger_onedrive_guard(self):
        local = b'[logs]\ntype = drive\nteam_drive = old\ntoken = OLD\n'
        remote = local.replace(b'team_drive = old', b'team_drive = new')
        self.assertFalse(merge.onedrive_identity_changed(remote, local))


if __name__ == "__main__":
    unittest.main()
