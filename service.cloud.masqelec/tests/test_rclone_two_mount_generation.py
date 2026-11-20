# -*- coding: utf-8 -*-
"""P0-B: generaciones y ABA sintéticos. No toca config real ni red."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_generation as gen
from lib import rclone_two_mount_plan as plan
from test_rclone_mount_isolation import wrapped_conf


class GenerationFenceTests(unittest.TestCase):
    def setUp(self):
        self.local = wrapped_conf("crypt")
        self.accounts = (plan.account_snapshot(self.local, 0),
                         plan.account_snapshot(self.local, 1))
        self.remote = self.local.replace(
            b"refresh-users_library_1", b"older-backup-refresh")
        self.sha = "a" * 40
        self.head = "b" * 40
        self.epochs = (10, 20, 30, 40)

    def capture(self, **updates):
        args = dict(canonical=self.local, accounts=self.accounts,
                    remote=self.remote, blob_sha=self.sha,
                    branch_head=self.head, epochs=self.epochs,
                    remote_authenticated=True, cooperative_epochs=True)
        args.update(updates)
        return gen.capture_window(**args)

    def check(self, window, **updates):
        args = dict(canonical=self.local, accounts=self.accounts,
                    remote=self.remote, blob_sha=self.sha,
                    branch_head=self.head, epochs=self.epochs,
                    remote_authenticated=True)
        args.update(updates)
        return gen.recheck_window(window, **args)

    def test_divergent_baseline_is_observable_but_never_published(self):
        w = self.capture()
        self.assertEqual(w.baseline, "baseline_diverged")
        self.assertEqual(self.check(w), "stable_for_lab_only")
        self.assertNotIn("older-backup-refresh", repr(w))
        self.assertNotIn(self.sha, repr(w))

    def test_matching_baseline_does_not_authorize_release(self):
        w = self.capture(remote=self.local)
        self.assertEqual(w.baseline, "baseline_equal")
        self.assertEqual(self.check(w, remote=self.local),
                         "stable_for_lab_only")

    def test_no_cooperative_epoch_guarantee_fails_closed(self):
        w = self.capture(cooperative_epochs=False)
        self.assertEqual(self.check(w), "blocked_untracked_writers")

    def test_aba_identical_bytes_but_changed_local_generation(self):
        w = self.capture()
        # rclone generó B y restauró A: bytes finales iguales,
        # pero el escritor cooperativo incrementó la revisión.
        self.assertEqual(self.check(w, epochs=(12, 20, 30, 40)),
                         "changed_generation")

    def test_remote_aba_requires_generation_counter(self):
        w = self.capture()
        self.assertEqual(self.check(w, epochs=(10, 20, 30, 42)),
                         "changed_generation")

    def test_changed_account1_generation_detected(self):
        w = self.capture()
        self.assertEqual(self.check(w, epochs=(10, 21, 30, 40)),
                         "changed_generation")

    def test_changed_account2_generation_detected(self):
        w = self.capture()
        self.assertEqual(self.check(w, epochs=(10, 20, 31, 40)),
                         "changed_generation")

    def test_account_bytes_change_without_generation_detected(self):
        w = self.capture()
        changed = (self.accounts[0].replace(
            b"refresh-users_library_1", b"changed-refresh"),
            self.accounts[1])
        self.assertEqual(self.check(w, accounts=changed), "changed_snapshot")

    def test_canonical_changes_even_access_token_only(self):
        w = self.capture()
        changed = self.local.replace(
            b"access-users_library_1", b"updated-access")
        self.assertEqual(self.check(w, canonical=changed), "changed_snapshot")

    def test_remote_changes_even_when_refresh_equal(self):
        w = self.capture()
        changed = self.remote.replace(
            b"access-users_library_1", b"new-access")
        self.assertEqual(self.check(w, remote=changed), "changed_snapshot")

    def test_git_branch_move_detected(self):
        w = self.capture()
        self.assertEqual(self.check(w, branch_head="c" * 40),
                         "changed_remote_revision")

    def test_git_blob_change_detected(self):
        w = self.capture()
        self.assertEqual(self.check(w, blob_sha="c" * 40),
                         "changed_remote_blob")

    def test_no_authenticated_remote_fails_closed(self):
        with self.assertRaises(ValueError):
            self.capture(remote_authenticated=False)
        w = self.capture()
        self.assertEqual(self.check(w, remote_authenticated=False),
                         "blocked_unverified_remote")

    def test_bad_epochs_and_boolean_epochs_blocked(self):
        for bad in (None, (0, 1, 2), (0, True, 2, 3),
                    (-1, 1, 2, 3), [0, 1, 2, 3]):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    self.capture(epochs=bad)
        w = self.capture()
        self.assertEqual(self.check(w, epochs=(1, 2)),
                         "blocked_invalid_sources")

    def test_mismatched_crypt_identity_rejected(self):
        broken = (self.accounts[0].replace(
            b"filename_encryption = off",
            b"filename_encryption = standard"), self.accounts[1])
        with self.assertRaises(ValueError):
            self.capture(accounts=broken)

    def test_wrong_account_order_rejected(self):
        with self.assertRaises(ValueError):
            self.capture(accounts=self.accounts[::-1])

    def test_undocumented_remote_static_drift_rejected(self):
        with self.assertRaises(ValueError):
            self.capture(remote=self.remote.replace(
                b"drive_type = personal", b"drive_type = business"))

    def test_wrong_sha_format_and_bool_trust_rejected(self):
        with self.assertRaises(ValueError):
            self.capture(blob_sha="bad")
        with self.assertRaises(ValueError):
            self.capture(cooperative_epochs=1)

    def test_none_or_unvalidated_window_fails_closed(self):
        self.assertEqual(self.check(None), "blocked_invalid_window")
        w = self.capture()
        self.assertEqual(self.check(w, canonical=None),
                         "blocked_invalid_sources")

    def test_repr_never_contains_secrets_or_digests(self):
        w = self.capture()
        info = repr(w)
        self.assertNotIn("refresh", info)
        self.assertNotIn("library", info)
        self.assertNotIn("HMAC", info)


if __name__ == "__main__":
    unittest.main()
