# -*- coding: utf-8 -*-
"""Conjunción P0-B/P0-C; no permite promoción de OAuth por coherencia local."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_fleet as fleet
from lib import rclone_two_mount_generation as generations
from lib import rclone_two_mount_fleet_gate as gate
from lib import rclone_two_mount_plan as plan
from test_rclone_mount_isolation import wrapped_conf


class CompositeFleetGateTests(unittest.TestCase):
    def setUp(self):
        self.local = wrapped_conf("crypt")
        self.remote = self.local
        self.accounts = (plan.account_snapshot(self.local, 0),
                         plan.account_snapshot(self.local, 1))
        self.members = (("master", "cooperative", True, 5, (0, 1)),
                        ("client", "cooperative", True, 8, (0, 1)))
        self.epoch = (10, 20, 30, 40)
        self.sha = "a" * 40
        self.head = "b" * 40
        self.w0 = fleet.begin_freeze(
            0, self.members, 7, "f" * 32, 100,
            inventory_authoritative=True, fleet_complete=True)["window"]
        self.w1 = fleet.begin_freeze(
            1, self.members, 7, "f" * 32, 100,
            inventory_authoritative=True, fleet_complete=True)["window"]
        self.g = self.generation()

    def generation(self, **updates):
        d = dict(canonical=self.local, accounts=self.accounts,
                 remote=self.remote, blob_sha=self.sha,
                 branch_head=self.head, epochs=self.epoch,
                 remote_authenticated=True, cooperative_epochs=True)
        d.update(updates)
        return generations.capture_window(**d)

    def ack(self, window, name):
        info = {m[0]: m for m in self.members}[name]
        return fleet.acknowledge_quiescence(
            window, name, window.challenge, info[3], 101,
            report_authenticated=True, mounts_stopped=True,
            refresh_path_fenced=True)

    def ready_fleet(self):
        for window in (self.w0, self.w1):
            for name in ("master", "client"):
                self.assertEqual(self.ack(window, name),
                                 "ack_recorded_lab_only")

    def check(self, **changes):
        opts = dict(first=self.w0, second=self.w1,
                    generation_window=self.g,
                    current_inventory=self.members,
                    registry_revision=7, now=103,
                    canonical=self.local, accounts=self.accounts,
                    remote=self.remote, blob_sha=self.sha,
                    branch_head=self.head, epochs=self.epoch,
                    registry_verified=True, fleet_complete=True,
                    remote_authenticated=True)
        opts.update(changes)
        return gate.evaluate_synthetic_fleet_gate(**opts)

    def test_all_fences_revalidated_only_in_lab(self):
        self.ready_fleet()
        self.assertEqual(self.check(), "dual_fence_lab_only")

    def test_real_baseline_divergence_never_auto_promotes(self):
        self.ready_fleet()
        old = self.local.replace(
            b"refresh-users_library_1", b"older-backup-token")
        diff = self.generation(remote=old)
        self.assertEqual(self.check(
            generation_window=diff, remote=old),
            "blocked_published_baseline_diverged")

    def test_uncoordinated_generation_blocks_with_full_fleet_acks(self):
        self.ready_fleet()
        g = self.generation(cooperative_epochs=False)
        self.assertEqual(self.check(generation_window=g),
                         "blocked_untracked_writers")

    def test_no_fleet_report_blocks_even_when_sources_consistent(self):
        self.assertEqual(self.check(), "blocked_missing_ack")

    def test_missing_account2_ack_blocks(self):
        for name in ("master", "client"):
            self.ack(self.w0, name)
        self.assertEqual(self.check(), "blocked_missing_ack")

    def test_writer_epoch_changed_after_fleet_ack_blocks(self):
        self.ready_fleet()
        changed = (("master", "cooperative", True, 6, (0, 1)), self.members[1])
        self.assertEqual(self.check(current_inventory=changed),
                         "blocked_writer_changed")

    def test_canonical_generation_aba_blocks(self):
        self.ready_fleet()
        self.assertEqual(self.check(epochs=(12, 20, 30, 40)),
                         "changed_generation")

    def test_local_account_change_detected(self):
        self.ready_fleet()
        changed = (self.accounts[0].replace(
            b"refresh-users_library_1", b"modified-refresh"),
            self.accounts[1])
        self.assertEqual(self.check(accounts=changed), "changed_snapshot")

    def test_mqc2_mutation_blocks(self):
        self.ready_fleet()
        other = self.local.replace(
            b"access-users_library_1", b"altered-access")
        self.assertEqual(self.check(remote=other), "changed_snapshot")

    def test_branch_revision_change_blocks(self):
        self.ready_fleet()
        self.assertEqual(self.check(branch_head="c" * 40),
                         "changed_remote_revision")

    def test_remote_authentication_loss_blocks(self):
        self.ready_fleet()
        self.assertEqual(self.check(remote_authenticated=False),
                         "blocked_unverified_remote")

    def test_inventory_incomplete_blocks_even_with_acks(self):
        self.ready_fleet()
        self.assertEqual(self.check(fleet_complete=False),
                         "blocked_inventory_untrusted")

    def test_fleet_window_wrong_cohort_blocks(self):
        self.ready_fleet()
        different = fleet.begin_freeze(
            1, self.members, 7, "e" * 32, 100,
            inventory_authoritative=True, fleet_complete=True)["window"]
        self.assertEqual(self.check(second=different),
                         "blocked_pair_inconsistent")

    def test_missing_generation_window_blocks(self):
        self.ready_fleet()
        self.assertEqual(self.check(generation_window=None),
                         "blocked_generation_window_missing")

    def test_expired_or_aborted_window_blocks(self):
        self.ready_fleet()
        self.assertEqual(self.check(now=160), "blocked_expired")
        fleet.abort_freeze(self.w0)
        self.assertEqual(self.check(), "blocked_aborted")

    def test_output_does_not_expose_secret_or_grant_write(self):
        self.ready_fleet()
        result = self.check()
        for forbidden in ("refresh", "users_library", "publish",
                          "authorized", "ready_for_live"):
            self.assertNotIn(forbidden, result)


if __name__ == "__main__":
    unittest.main()
