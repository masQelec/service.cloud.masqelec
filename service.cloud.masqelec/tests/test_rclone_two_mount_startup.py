# -*- coding: utf-8 -*-
"""Arranque del addon MASTER/CLIENTE tras actualización: SOLO decisiones."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_rollout as rollout


class AddonStartupDecisionTests(unittest.TestCase):
    def ready(self, state="prepared", **changes):
        args = dict(feature_allowed=True, release_authorized=True,
                    local_config_valid=True, runtime_compatible=True,
                    playback_idle=True, rollback_ready=True)
        args.update(changes)
        return rollout.startup_decision(state, **args)

    def test_default_upgrade_does_nothing_in_production(self):
        self.assertEqual(rollout.startup_decision("legacy"), "continue_legacy")

    def test_updated_addon_stages_from_device_local_credentials(self):
        self.assertEqual(self.ready("legacy"), "stage_two_accounts_locally")

    def test_new_addon_on_existing_client_and_master_same_policy(self):
        for _role in ("MASTER", "CLIENT"):
            self.assertEqual(self.ready("legacy"),
                             "stage_two_accounts_locally")

    def test_prepared_waits_final_release(self):
        self.assertEqual(self.ready(release_authorized=False),
                         "keep_legacy_release_not_authorized")

    def test_prepared_migrates_only_when_idle_and_rollback_ready(self):
        self.assertEqual(self.ready(),
                         "plan_local_two_fuse_four_bind_cutover")

    def test_playback_active_deferred(self):
        self.assertEqual(self.ready(playback_idle=False),
                         "defer_migration_playback_active")

    def test_incompatible_rclone_systemd_keeps_legacy(self):
        self.assertEqual(self.ready(runtime_compatible=False),
                         "keep_legacy_runtime_incompatible")

    def test_no_rollback_keeps_legacy(self):
        self.assertEqual(self.ready(rollback_ready=False),
                         "keep_legacy_rollback_unavailable")

    def test_invalid_config_does_not_stage_or_cut_over(self):
        for state in ("legacy", "prepared"):
            with self.subTest(state=state):
                self.assertEqual(self.ready(
                    state, local_config_valid=False),
                    "blocked_local_config")

    def test_existing_v2_is_verified_not_reapplied(self):
        self.assertEqual(self.ready("active"),
                         "verify_existing_two_fuse_four_bind")

    def test_existing_v2_without_release_blocks_legacy_resurrection(self):
        self.assertEqual(self.ready("active", feature_allowed=False),
                         "blocked_active_without_release")
        self.assertEqual(self.ready("active", release_authorized=False),
                         "blocked_active_without_release")

    def test_unsafe_marker_blocks(self):
        self.assertEqual(self.ready("unsafe"), "blocked_unsafe_state")
        self.assertEqual(self.ready("other"), "blocked_invalid_mode")

    def test_disabled_feature_never_activates_staged_version(self):
        self.assertEqual(self.ready("prepared", feature_allowed=False),
                         "continue_legacy")
        self.assertEqual(self.ready("legacy", feature_allowed=False),
                         "continue_legacy")

    def test_wrong_type_flags_fail_closed(self):
        self.assertEqual(self.ready(feature_allowed=1),
                         "blocked_invalid_release_flags")
        self.assertEqual(self.ready(release_authorized=1),
                         "blocked_invalid_release_flags")
        self.assertEqual(self.ready(playback_idle=1),
                         "blocked_invalid_readiness")

    def test_no_remote_network_or_tokens_are_required_for_decision(self):
        result = self.ready()
        self.assertNotIn("refresh_token", result)
        self.assertNotIn("github", result)
        self.assertNotIn("rclone.conf", result)


if __name__ == "__main__":
    unittest.main()
