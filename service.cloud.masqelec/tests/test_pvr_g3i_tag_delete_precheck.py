"""G3-I no-write gate tests: no TVH/Kodi requests made by fixtures."""
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

PATH = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3i_tag_delete_precheck.py"
SPEC = importlib.util.spec_from_file_location("pvr_g3i_precheck", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class PrecheckTests(TestCase):
    def setUp(self):
        self.tags = [{"uuid": MOD.TARGET_UUID, "name": MOD.TARGET_NAME,
                      "internal": False}]
        self.channels = [{"uuid": "ch1", "tags": ["elsewhere"]}]
        self.kodi = [{"label": MOD.TARGET_NAME}]

    def perform(self, groups=None, channels=None, tags=None, kodi=None):
        grids = {
            "channeltag/grid": self.tags if tags is None else tags,
            "channel/grid": self.channels if channels is None else channels,
        }
        with patch.object(MOD, "_m3u_groups", return_value=(set() if groups is None else groups, 1)), \
             patch.object(MOD, "_grid", side_effect=lambda endpoint, limit: grids[endpoint]), \
             patch.object(MOD, "_kodi_groups", return_value=self.kodi if kodi is None else kodi), \
             patch.object(MOD, "_tag_definition_readable", return_value=True) as read:
            output = StringIO()
            with redirect_stdout(output):
                code = MOD.inspect()
            return code, output.getvalue(), read.called

    def test_clean_candidate_stays_not_authorized(self):
        code, report, read = self.perform()
        self.assertEqual(code, 0)
        self.assertIn("PRECHECK=PASS", report)
        self.assertIn("DELETE_AUTHORIZED=NO", report)
        self.assertTrue(read)

    def test_live_group_blocks(self):
        code, report, read = self.perform(groups={MOD.TARGET_NAME})
        self.assertEqual(code, 2)
        self.assertIn("PRECHECK=BLOCKED", report)
        self.assertFalse(read)

    def test_tag_with_channels_blocks(self):
        self.channels[0]["tags"].append(MOD.TARGET_UUID)
        self.assertEqual(self.perform()[0], 2)

    def test_missing_kodi_group_blocks(self):
        self.assertEqual(self.perform(kodi=[])[0], 2)

    def test_duplicate_tag_name_blocks(self):
        self.tags.append({"uuid": "other", "name": MOD.TARGET_NAME, "internal": False})
        self.assertEqual(self.perform()[0], 2)

    def test_internal_tag_blocks(self):
        self.tags[0]["internal"] = True
        self.assertEqual(self.perform()[0], 2)

    def test_missing_channel_tags_field_blocks(self):
        self.channels[0].pop("tags")
        self.assertEqual(self.perform()[0], 2)

    def test_count_mismatch_blocks(self):
        self.channels.append({"uuid": "ch2", "tags": []})
        self.assertEqual(self.perform()[0], 2)

    def test_write_endpoints_rejected(self):
        with self.assertRaisesRegex(ValueError, "ENDPOINT_NOT_ALLOWED"):
            MOD._grid("idnode/delete", 10)
