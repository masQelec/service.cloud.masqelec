"""G3-Z2 offline unit tests; no network or production access."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3z2_service_resolution_lab.py"
spec = importlib.util.spec_from_file_location("g3z2", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

C1 = "a" * 32
C2 = "b" * 32
S1 = "1" * 32
S2 = "2" * 32


def ch(rows):
    return {"total": len(rows), "entries": rows}


def svc(*ids):
    return {"entries": [{"key": k, "val": "secret-name"} for k in ids]}


class ServiceResolutionTests(unittest.TestCase):
    def test_two_resolve(self):
        r = m.evaluate(ch([{"uuid": C1, "services": [S1]},
                           {"uuid": C2, "services": [S2]}]), svc(S1, S2))
        self.assertEqual(r["unresolved_references"], 0)
        self.assertEqual(r["tvh_channel_service_reference_proven"], "YES")

    def test_unresolved_is_not_proof(self):
        r = m.evaluate(ch([{"uuid": C1, "services": [S2]}]), svc(S1))
        self.assertEqual(r["unresolved_references"], 1)
        self.assertEqual(r["tvh_channel_service_reference_proven"], "NO")

    def test_channel_without_service_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "CHANNEL_WITHOUT_SERVICE"):
            m.evaluate(ch([{"uuid": C1, "services": []}]), svc(S1))

    def test_bad_reference_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "INVALID_SERVICE_REFERENCE"):
            m.evaluate(ch([{"uuid": C1, "services": ["bad"]}]), svc(S1))

    def test_duplicate_reference_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "DUPLICATE_SERVICE_REFERENCE"):
            m.evaluate(ch([{"uuid": C1, "services": [S1, S1]}]), svc(S1))

    def test_duplicate_service_id_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "DUPLICATE_SERVICE_LIST_ID"):
            m.evaluate(ch([{"uuid": C1, "services": [S1]}]), svc(S1, S1))

    def test_duplicate_channel_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "DUPLICATE_CHANNEL_UUID"):
            m.evaluate(ch([{"uuid": C1, "services": [S1]},
                           {"uuid": C1, "services": [S1]}]), svc(S1))

    def test_incomplete_channels_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "INCOMPLETE_INVENTORY"):
            m.evaluate({"total": 2, "entries": [{"uuid": C1, "services": [S1]}]}, svc(S1))

    def test_empty_inventory_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "INCOMPLETE_INVENTORY"):
            m.evaluate(ch([]), svc(S1))

    def test_invalid_service_id_blocks(self):
        with self.assertRaisesRegex(m.Blocked, "INVALID_SERVICE_LIST_ID"):
            m.evaluate(ch([{"uuid": C1, "services": [S1]}]), svc("bad"))

    def test_never_proves_kodi_or_cuid(self):
        r = m.evaluate(ch([{"uuid": C1, "services": [S1]}]), svc(S1))
        self.assertEqual(r["cuid_mapping_proven"], "NO")
        self.assertEqual(r["tvh_to_kodi_identity_proven"], "NO")
        self.assertEqual(r["deletion_authorized"], "NO")

    def test_no_secret_values_in_report(self):
        r = m.evaluate(ch([{"uuid": C1, "name": "secret-channel",
                            "services": [S1]}]), svc(S1))
        text = str(r)
        for secret in (C1, S1, "secret-channel", "secret-name"):
            self.assertNotIn(secret, text)

    def test_service_shared_between_two_channels_is_not_identity(self):
        r = m.evaluate(ch([{"uuid": C1, "services": [S1]},
                           {"uuid": C2, "services": [S1]}]), svc(S1))
        self.assertEqual(r["unique_referenced_services"], 1)
        self.assertEqual(r["service_reference_count"], 2)


if __name__ == "__main__":
    unittest.main()
