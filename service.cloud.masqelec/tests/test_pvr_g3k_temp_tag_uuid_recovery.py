"""G3-K tests use a fake in-memory TVH API. No network or TVH files."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3k_temp_tag_uuid_recovery.py"
SPEC = importlib.util.spec_from_file_location("pvr_g3k_temp_tag_uuid_recovery", SCRIPT)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class TemporaryTagRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.base = [
            {"uuid": MOD.HISTORIC_UUID, "name": "ES - NBA", "internal": False}
        ] + [
            {"uuid": "baseline-%02d" % i, "name": "Base %02d" % i,
             "internal": False} for i in range(31)
        ]
        self.tags = [dict(t) for t in self.base]
        self.channels = [{"uuid": "channel-%03d" % i, "tags": ["baseline-00"]}
                         for i in range(720)]
        self.next_id = 0
        self.accept_uuid = False

    def fake_grid(self, path, limit):
        if path == "channeltag/grid":
            return [dict(x) for x in self.tags]
        if path == "channel/grid":
            return [dict(x) for x in self.channels]
        raise AssertionError("Unexpected endpoint")

    def fake_api(self, path, params=None, post=False):
        import json
        if path == "channeltag/create" and post:
            definition = json.loads(params["conf"])
            self.next_id += 1
            uuid = definition.get("uuid") if self.accept_uuid else None
            if not uuid:
                uuid = "new-" + str(self.next_id)
            self.tags.append({
                "name": definition["name"], "uuid": uuid, "internal": False
            })
            return {}
        if path == "idnode/delete" and post:
            uid = params["uuid"]
            self.assertNotIn(uid, {x["uuid"] for x in self.base})
            self.tags = [x for x in self.tags if x["uuid"] != uid]
            return {}
        raise AssertionError("Unexpected API")

    def run_experiment(self):
        with patch.object(MOD, "grid", side_effect=self.fake_grid), \
             patch.object(MOD, "api", side_effect=self.fake_api):
            output = StringIO()
            with redirect_stdout(output):
                result = MOD.experiment()
            return result, output.getvalue()

    def test_uuid_ignored_fails_closed_and_restores_inventory(self):
        result, report = self.run_experiment()
        self.assertEqual(result, 2)
        self.assertIn("UUID_RECREATED_SAME=NO", report)
        self.assertIn("INVENTORY_RESTORED=PASS", report)
        self.assertEqual(self.tags, self.base)

    def test_uuid_accepted_still_not_full_rollback_proof(self):
        self.accept_uuid = True
        result, report = self.run_experiment()
        self.assertEqual(result, 0)
        self.assertIn("UUID_RECREATED_SAME=YES", report)
        self.assertIn("FULL_CONFIGURATION_RESTORE_PROVEN=NO", report)
        self.assertEqual(self.tags, self.base)

    def test_baseline_count_prevents_write(self):
        self.tags.pop()
        with patch.object(MOD, "grid", side_effect=self.fake_grid), \
             patch.object(MOD, "api", side_effect=AssertionError("write attempted")):
            with self.assertRaisesRegex(ValueError, "UNEXPECTED_BASELINE"):
                MOD.experiment()

    def test_preexisting_uuid_cannot_be_deleted(self):
        with patch.object(MOD, "grid", side_effect=self.fake_grid):
            with self.assertRaisesRegex(ValueError, "UNSAFE_DISPOSABLE_IDENTITY"):
                MOD.safe_delete(self.base[0], "ES - NBA",
                                {row["uuid"] for row in self.base})

    def test_occupied_disposable_cannot_be_deleted(self):
        disposable = {"uuid": "disposable", "name": "MASQELEC_G3K_TEST",
                      "internal": False}
        self.tags.append(disposable)
        self.channels[0]["tags"].append("disposable")
        with patch.object(MOD, "grid", side_effect=self.fake_grid), \
             patch.object(MOD, "api", side_effect=AssertionError("delete attempted")):
            with self.assertRaisesRegex(ValueError, "DISPOSABLE_HAS_CHANNELS"):
                MOD.safe_delete(disposable, disposable["name"],
                                {row["uuid"] for row in self.base})

    def test_create_conf_contains_requested_uuid(self):
        calls = []
        with patch.object(MOD, "api", side_effect=lambda *a, **k: calls.append((a, k))):
            MOD.create("MASQELEC_G3K_TEST", requested_uuid="requested-test-uuid")
        import json
        config = json.loads(calls[0][0][1]["conf"])
        self.assertEqual(config["uuid"], "requested-test-uuid")


if __name__ == "__main__":
    unittest.main()
