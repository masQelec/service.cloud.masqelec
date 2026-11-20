"""G3-Q policy tests: dry-run only; no Kodi/TVH calls."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.pvr_update_policy import classify


class PVRUpdatePolicyTests(unittest.TestCase):
    def classify(self, **kwargs):
        defaults = dict(playlist_changed=False, db_mismatch=False)
        defaults.update(kwargs)
        return classify(**defaults)

    def test_unchanged_needs_no_reset(self):
        got = self.classify()
        self.assertEqual(got["status"], "NO_RESET_NEEDED")
        self.assertFalse(got["legacy_soft_reset"])
        self.assertFalse(got["non_disruptive_cutover_authorized"])

    def test_playlist_change_requires_legacy_until_proven(self):
        got = self.classify(playlist_changed=True)
        self.assertEqual(got["reason"], "TVH_READY_NOT_PROVEN")
        self.assertTrue(got["legacy_soft_reset"])

    def test_db_mismatch_requires_legacy_until_proven(self):
        got = self.classify(db_mismatch=True)
        self.assertTrue(got["legacy_soft_reset"])

    def test_both_changes_require_legacy(self):
        got = self.classify(playlist_changed=True, db_mismatch=True)
        self.assertTrue(got["legacy_soft_reset"])

    def test_ready_without_refetch_denied(self):
        got = self.classify(playlist_changed=True, tvh_ready=True)
        self.assertEqual(got["reason"], "M3U_REFETCH_NOT_PROVEN")

    def test_refetch_without_identity_denied(self):
        got = self.classify(playlist_changed=True, tvh_ready=True,
                            refetch_confirmed=True)
        self.assertEqual(got["reason"], "CHANNEL_IDENTITY_NOT_PROVEN")

    def test_identity_without_group_links_denied(self):
        got = self.classify(playlist_changed=True, tvh_ready=True,
                            refetch_confirmed=True, channel_identity_confirmed=True)
        self.assertEqual(got["reason"], "CHANNEL_GROUP_LINKS_NOT_PROVEN")

    def test_group_links_without_kodi_denied(self):
        got = self.classify(playlist_changed=True, tvh_ready=True,
                            refetch_confirmed=True, channel_identity_confirmed=True,
                            group_links_confirmed=True)
        self.assertEqual(got["reason"], "KODI_CONVERGENCE_NOT_PROVEN")

    def test_all_evidence_does_not_auto_authorize(self):
        got = self.classify(playlist_changed=True, tvh_ready=True,
                            refetch_confirmed=True, channel_identity_confirmed=True,
                            group_links_confirmed=True, kodi_confirmed=True)
        self.assertEqual(got["reason"], "ALL_EVIDENCE_REQUIRES_MANUAL_CUTOVER_REVIEW")
        self.assertFalse(got["non_disruptive_cutover_authorized"])

    def test_non_boolean_denied(self):
        with self.assertRaisesRegex(ValueError, "INVALID_BOOLEAN_INPUT"):
            self.classify(playlist_changed=1)

    def test_unknown_ready_denied(self):
        with self.assertRaisesRegex(ValueError, "INVALID_TVH_STATE"):
            self.classify(playlist_changed=True, tvh_ready="yes")

    def test_never_enables_any_cutover(self):
        for p in (False, True):
            for d in (False, True):
                got = self.classify(
                    playlist_changed=p, db_mismatch=d, tvh_ready=True,
                    refetch_confirmed=True, channel_identity_confirmed=True,
                    group_links_confirmed=True, kodi_confirmed=True)
                self.assertFalse(got["non_disruptive_cutover_authorized"])


if __name__ == "__main__":
    unittest.main()
