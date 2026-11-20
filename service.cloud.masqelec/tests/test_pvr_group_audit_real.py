"""G3 live audit runner tests. No calls to real TVH or filesystem writes."""
from contextlib import redirect_stdout
import importlib.util
from io import StringIO
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "tools" / "pvr_group_audit_real.py"
SPEC = importlib.util.spec_from_file_location("pvr_group_audit_real", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class LiveAuditRunnerTests(TestCase):
    def test_rejects_write_endpoints(self):
        with self.assertRaisesRegex(ValueError, "INVALID_API_ENDPOINT"):
            MOD._grid("idnode/delete", 10)

    def test_uses_standalone_package_module(self):
        fn = MOD._load_auditor()
        self.assertTrue(callable(fn))

    def test_sanitized_success_output(self):
        fake_result = {
            "status": "DIAGNOSTIC_ONLY", "reason": "NAME_AND_NUMBER_NOT_TECHNICAL_IDENTITY",
            "m3u_channels": 720, "tvh_channels": 720,
            "exact_unique_name_pairs": 696, "number_disambiguated_pairs": 24,
            "resolved_pairs": 720, "unresolved_m3u_channels": 0,
            "group_mismatch_count": 0, "apply_authorized": False,
            "group_mismatch_samples": [{"channel_name": "secret"}],
        }
        with patch.object(MOD, "_load_auditor", return_value=lambda *args: fake_result), \
             patch.object(MOD, "_read_playlist", return_value="secret:password"), \
             patch.object(MOD, "_grid", return_value={"entries": [], "total": 0}):
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(MOD.run(), 0)
            self.assertIn("RESOLVED_PAIRS=720", output.getvalue())
            self.assertNotIn("secret", output.getvalue())
            self.assertNotIn("password", output.getvalue())
            self.assertIn("APPLY_AUTHORIZED=NO", output.getvalue())

    def test_mismatch_exit_nonzero(self):
        fake_result = {"status": "DIAGNOSTIC_ONLY", "group_mismatch_count": 1}
        with patch.object(MOD, "_load_auditor", return_value=lambda *args: fake_result), \
             patch.object(MOD, "_read_playlist", return_value="#EXTM3U"), \
             patch.object(MOD, "_grid", return_value={"entries": [], "total": 0}):
            with redirect_stdout(StringIO()):
                self.assertEqual(MOD.run(), 2)
