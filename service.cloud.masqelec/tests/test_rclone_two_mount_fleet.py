# -*- coding: utf-8 -*-
"""P0-C: simular conflictos, flota incompleta, ABA y cercos OAuth sin IO."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_fleet as fleet


class OAuthFleetFences(unittest.TestCase):
    def setUp(self):
        self.members = (
            ("master", "cooperative", True, 13, (0, 1)),
            ("client-a", "cooperative", True, 7, (0, 1)),
            ("client-b", "cooperative", True, 11, (0, 1)),
        )
        self.revision = 12
        self.cohort = "a" * 32

    def start(self, account=0, **options):
        args = dict(inventory=self.members, revision=self.revision,
                    cohort=self.cohort, now=100,
                    inventory_authoritative=True, fleet_complete=True)
        args.update(options)
        return fleet.begin_freeze(account, **args)

    def ack(self, w, member, **options):
        index = {m[0]: m for m in self.members}
        args = dict(challenge=w.challenge, writer_epoch=index[member][3],
                    now=101, report_authenticated=True,
                    mounts_stopped=True, refresh_path_fenced=True)
        args.update(options)
        return fleet.acknowledge_quiescence(w, member, **args)

    def assess(self, window, **options):
        args = dict(current_inventory=self.members,
                    revision=self.revision, now=110,
                    inventory_authoritative=True, fleet_complete=True)
        args.update(options)
        return fleet.assess_freeze(window, **args)

    def all_ack(self, window):
        for m in self.members:
            self.assertEqual(self.ack(window, m[0]),
                             "ack_recorded_lab_only")

    def test_inventory_untrusted_denied_without_window(self):
        r = self.start(inventory_authoritative=False)
        self.assertEqual(r["status"], "blocked_inventory_untrusted")
        self.assertIsNone(r["window"])

    def test_incomplete_fleet_denied(self):
        self.assertEqual(self.start(fleet_complete=False)["status"],
                         "blocked_inventory_untrusted")

    def test_legacy_member_cannot_silently_quiesce(self):
        members = self.members + (
            ("legacy-old", "legacy", True, 1, (0,)),)
        self.assertEqual(self.start(inventory=members)["status"],
                         "blocked_legacy_writers")

    def test_unknown_writer_fails_closed(self):
        members = self.members + (
            ("unidentified", "unknown", True, 1, (0,)),)
        self.assertEqual(self.start(inventory=members)["status"],
                         "blocked_unknown_writer")

    def test_offline_account_member_blocks(self):
        members = self.members + (
            ("remote-offline", "cooperative", False, 1, (0,)),)
        self.assertEqual(self.start(inventory=members)["status"],
                         "blocked_offline_member")

    def test_duplicate_member_id_rejected(self):
        with self.assertRaises(ValueError):
            self.start(inventory=self.members + (self.members[0],))

    def test_invalid_device_mode_rejected(self):
        bad = (("m", "root", True, 1, (0,)),)
        with self.assertRaises(ValueError):
            self.start(inventory=bad)

    def test_no_writers_in_account_blocks(self):
        members = (("only-1", "cooperative", True, 2, (1,)),)
        self.assertEqual(self.start(inventory=members)["status"],
                         "blocked_no_writers_in_scope")

    def test_first_freeze_cannot_progress_without_all_acks(self):
        w = self.start()["window"]
        self.assertEqual(self.assess(w), "blocked_missing_ack")
        self.assertEqual(self.ack(w, "master"), "ack_recorded_lab_only")
        self.assertEqual(self.assess(w), "blocked_missing_ack")

    def test_valid_cooperative_simulation_lab_only(self):
        w = self.start()["window"]
        self.all_ack(w)
        self.assertEqual(self.assess(w), "quiescent_lab_only")
        self.assertNotIn("client-a", repr(w))
        self.assertNotIn(w.challenge, repr(w))

    def test_stale_challenge_from_old_attempt_denied(self):
        one = self.start()["window"]
        two = self.start()["window"]
        self.assertNotEqual(one.challenge, two.challenge)
        self.assertEqual(self.ack(two, "master", challenge=one.challenge),
                         "blocked_stale_challenge")
        self.assertEqual(self.assess(two), "blocked_missing_ack")

    def test_untrusted_report_denied(self):
        w = self.start()["window"]
        self.assertEqual(self.ack(w, "master", report_authenticated=False),
                         "blocked_writer_not_quiescent")

    def test_mount_still_live_denied(self):
        w = self.start()["window"]
        self.assertEqual(self.ack(w, "master", mounts_stopped=False),
                         "blocked_writer_not_quiescent")

    def test_refresh_not_fenced_denied(self):
        w = self.start()["window"]
        self.assertEqual(self.ack(w, "master", refresh_path_fenced=False),
                         "blocked_writer_not_quiescent")

    def test_writer_epoch_different_at_ack_denied(self):
        w = self.start()["window"]
        self.assertEqual(self.ack(w, "master", writer_epoch=14),
                         "blocked_writer_changed")

    def test_unknown_ack_sender_denied(self):
        w = self.start()["window"]
        self.assertEqual(fleet.acknowledge_quiescence(
            w, "intruder", w.challenge, 1, 102,
            report_authenticated=True, mounts_stopped=True,
            refresh_path_fenced=True), "blocked_unknown_member")

    def test_duplicate_ack_idempotent_lab_only(self):
        w = self.start()["window"]
        self.assertEqual(self.ack(w, "master"), "ack_recorded_lab_only")
        self.assertEqual(self.ack(w, "master"), "duplicate_ack_lab_only")

    def test_join_after_acks_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        extra = self.members + (("client-new", "cooperative", True, 1, (0,)),)
        self.assertEqual(self.assess(
            w, current_inventory=extra),
            "blocked_membership_changed")

    def test_device_leaves_after_acks_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        self.assertEqual(self.assess(
            w, current_inventory=self.members[:-1]),
            "blocked_membership_changed")

    def test_device_disconnects_after_ack_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        changed = self.members[:-1] + (
            ("client-b", "cooperative", False, 11, (0, 1)),)
        self.assertEqual(self.assess(
            w, current_inventory=changed),
            "blocked_offline_member")

    def test_writer_refresh_event_after_ack_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        changed = (("master", "cooperative", True, 14, (0, 1)),
                   *self.members[1:])
        self.assertEqual(self.assess(
            w, current_inventory=changed),
            "blocked_writer_changed")

    def test_aba_same_final_generation_only_detected_if_incremented(self):
        w = self.start()["window"]
        self.all_ack(w)
        # No proof if untracked writer went A->B->A without bump!
        self.assertEqual(self.assess(w), "quiescent_lab_only")
        changed = self.members[:1] + (
            ("client-a", "cooperative", True, 9, (0, 1)),) + self.members[2:]
        self.assertEqual(self.assess(
            w, current_inventory=changed), "blocked_writer_changed")

    def test_registry_revision_changed_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        self.assertEqual(self.assess(w, revision=13),
                         "blocked_inventory_revision_changed")

    def test_invalid_clock_and_expiry_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        self.assertEqual(self.assess(w, now=99), "blocked_invalid_clock")
        self.assertEqual(self.assess(w, now=160), "blocked_expired")
        self.assertEqual(self.ack(w, "master", now=160), "blocked_expired")

    def test_timeout_does_not_auto_authorize_takeover(self):
        w = self.start()["window"]
        self.all_ack(w)
        self.assertEqual(self.assess(w, now=160), "blocked_expired")
        # Even with reports, no automatic lease release/reassignment exists.
        self.assertEqual(self.assess(w, now=161), "blocked_expired")

    def test_abort_is_irreversible_for_this_window(self):
        w = self.start()["window"]
        self.assertEqual(fleet.abort_freeze(w), "aborted_lab_only")
        self.assertEqual(self.ack(w, "master"), "blocked_aborted")
        self.assertEqual(self.assess(w), "blocked_aborted")

    def test_mode_changes_during_window_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        changed = (("master", "legacy", True, 13, (0, 1)),
                   *self.members[1:])
        self.assertEqual(self.assess(
            w, current_inventory=changed), "blocked_membership_changed")

    def test_invalid_inventory_after_open_blocks(self):
        w = self.start()["window"]
        self.all_ack(w)
        self.assertEqual(self.assess(w, current_inventory=()),
                         "blocked_invalid_inventory")

    def test_invalid_epoch_and_account_definitions_rejected(self):
        for records in (
            (("a", "cooperative", True, True, (0,)),),
            (("a", "cooperative", True, -1, (0,)),),
            (("a", "cooperative", True, 1, (0, 0)),),
            (("a", "cooperative", True, 1, (False,)),),
        ):
            with self.subTest(records=records):
                with self.assertRaises(ValueError):
                    self.start(inventory=records)

    def test_scope_requires_integer_account(self):
        with self.assertRaises(ValueError):
            self.start(account=True)  # uses method account override separately

    def test_pair_requires_both_quiescent_same_cohort(self):
        first = self.start(0)["window"]
        second = self.start(1)["window"]
        self.all_ack(first)
        self.all_ack(second)
        self.assertEqual(fleet.assess_canonical_pair(
            first, second, self.members, self.revision, 110,
            inventory_authoritative=True, fleet_complete=True),
            "both_accounts_quiescent_lab_only")

    def test_pair_incomplete_account2_denied(self):
        first = self.start(0)["window"]
        second = self.start(1)["window"]
        self.all_ack(first)
        self.assertEqual(fleet.assess_canonical_pair(
            first, second, self.members, self.revision, 110,
            inventory_authoritative=True, fleet_complete=True),
            "blocked_missing_ack")

    def test_pair_different_cohorts_denied(self):
        first = self.start(0)["window"]
        second = self.start(1, cohort="b" * 32)["window"]
        self.all_ack(first)
        self.all_ack(second)
        self.assertEqual(fleet.assess_canonical_pair(
            first, second, self.members, self.revision, 110,
            inventory_authoritative=True, fleet_complete=True),
            "blocked_pair_inconsistent")

    def test_pair_wrong_order_denied(self):
        a = self.start(0)["window"]
        b = self.start(1)["window"]
        self.assertEqual(fleet.assess_canonical_pair(
            b, a, self.members, self.revision, 110,
            inventory_authoritative=True, fleet_complete=True),
            "blocked_pair_inconsistent")

    def test_false_claim_of_trusted_fleet_cannot_grant_publish(self):
        a = self.start(0)["window"]
        b = self.start(1)["window"]
        self.all_ack(a)
        self.all_ack(b)
        status = fleet.assess_canonical_pair(
            a, b, self.members, self.revision, 110,
            inventory_authoritative=True, fleet_complete=True)
        self.assertIn("lab_only", status)
        self.assertNotIn("publish", status)
        self.assertNotIn("authorized", status)


if __name__ == "__main__":
    unittest.main()
