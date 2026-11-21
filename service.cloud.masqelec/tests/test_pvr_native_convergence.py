"""G3-X strict read-only convergence policy tests; no Kodi or TVH needed."""
import importlib.util
import pathlib
import unittest

MODULE = pathlib.Path(__file__).resolve().parents[1] / "lib" / "pvr_native_convergence.py"
spec = importlib.util.spec_from_file_location("pvr_native_convergence", MODULE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def tvh(*names):
    return [{"uuid": "uuid-" + str(i), "name": n} for i, n in enumerate(names, 1)]


def kodi(*names):
    return [{"channelid": i, "label": n} for i, n in enumerate(names, 1)]


def check(a, b, **kwargs):
    return m.classify(a, b, tvh_total=len(a), kodi_total=len(b), **kwargs)


class NativeShadowTests(unittest.TestCase):
    def test_exact_match_is_not_identity(self):
        r = check(tvh("A", "B"), kodi("A", "B"))
        self.assertEqual(r["status"], "DESCRIPTIVE_MATCH")
        self.assertFalse(r["cuid_mapping_proven"])
        self.assertFalse(r["native_orphan_removal_proven"])

    def test_added_channel_not_yet_kodi(self):
        r = check(tvh("A", "B", "C"), kodi("A", "B"))
        self.assertEqual(r["status"], "DESCRIPTIVE_MISMATCH")

    def test_removed_channel_stale_kodi(self):
        r = check(tvh("A", "B"), kodi("A", "B", "C"))
        self.assertEqual(r["status"], "DESCRIPTIVE_MISMATCH")

    def test_removed_channel_converged_is_only_snapshot(self):
        r = check(tvh("A", "B"), kodi("A", "B"))
        self.assertEqual(r["reason"], "SINGLE_SNAPSHOT_NOT_IDENTITY_PROOF")

    def test_duplicate_names_block_identity_proof(self):
        r = check(tvh("A", "A"), kodi("A", "A"))
        self.assertEqual(r["status"], "DESCRIPTIVE_AMBIGUOUS")
        self.assertGreater(r["ambiguous_names"], 0)

    def test_same_counts_but_wrong_name(self):
        self.assertEqual(check(tvh("A", "B"), kodi("A", "X"))["status"], "DESCRIPTIVE_MISMATCH")

    def test_truncated_tvh(self):
        self.assertEqual(m.classify(tvh("A"), kodi("A"), tvh_total=2, kodi_total=1)["reason"], "INCOMPLETE_API_SNAPSHOT")

    def test_truncated_kodi(self):
        self.assertEqual(m.classify(tvh("A"), kodi("A"), tvh_total=1, kodi_total=2)["reason"], "INCOMPLETE_API_SNAPSHOT")

    def test_zero_channels_blocked(self):
        self.assertEqual(m.classify([], [], tvh_total=0, kodi_total=0)["status"], "BLOCKED")

    def test_missing_uuid_blocked(self):
        self.assertEqual(check([{"name": "A"}], kodi("A"))["reason"], "MISSING_ID")

    def test_duplicate_uuid_blocked(self):
        self.assertEqual(check([{"name":"A","uuid":"x"},{"name":"B","uuid":"x"}], kodi("A","B"))["reason"], "DUPLICATE_ID")

    def test_duplicate_kodi_id_blocked(self):
        self.assertEqual(check(tvh("A","B"), [{"label":"A","channelid":1},{"label":"B","channelid":1}])["reason"], "DUPLICATE_ID")

    def test_non_bool_non_int_total_fails(self):
        self.assertEqual(m.classify(tvh("A"), kodi("A"), tvh_total=True, kodi_total=1)["status"], "BLOCKED")

    def test_name_reorder_does_not_change_descriptive_match(self):
        self.assertEqual(check(tvh("A","B"), kodi("B","A"))["status"], "DESCRIPTIVE_MATCH")

    def test_no_case_folding_concealment(self):
        self.assertEqual(check(tvh("Channel"), kodi("channel"))["status"], "DESCRIPTIVE_MISMATCH")

    def test_never_authorizes_mutation(self):
        for r in (check(tvh("A"), kodi("A")), check(tvh("A"), kodi("B")),
                  check(tvh("A", "A"), kodi("A", "A"))):
            self.assertFalse(r["delete_authorized"])
            self.assertFalse(r["cutover_authorized"])


if __name__ == "__main__":
    unittest.main()
