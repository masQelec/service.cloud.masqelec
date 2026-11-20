"""G3-G read-only Kodi group order inspector tests."""
import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

PATH = Path(__file__).resolve().parents[1] / "tools" / "pvr_g3g_kodi_groups_readonly.py"
SPEC = importlib.util.spec_from_file_location("pvr_g3g_kodi_groups_readonly", PATH)
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


class G3GTests(TestCase):
    def test_order_match(self):
        tags = [{"name": "A", "uuid": "1"}, {"name": "B", "uuid": "2"}]
        groups = [{"label": "All channels"}, {"label": "A"}, {"label": "B"}]
        with patch.object(MOD, "get_m3u_groups", return_value=["A", "B"]), \
             patch.object(MOD, "get_tvh_tags", return_value=tags), \
             patch.object(MOD, "get_kodi_groups", return_value=groups):
            stream = StringIO()
            with redirect_stdout(stream):
                MOD.inspect()
            self.assertIn("KODI_ORDER_MATCH=YES", stream.getvalue())
            self.assertIn("APPLY_AUTHORIZED=NO", stream.getvalue())

    def test_order_mismatch(self):
        tags = [{"name": "A"}, {"name": "B"}]
        groups = [{"label": "B"}, {"label": "A"}]
        with patch.object(MOD, "get_m3u_groups", return_value=["A", "B"]), \
             patch.object(MOD, "get_tvh_tags", return_value=tags), \
             patch.object(MOD, "get_kodi_groups", return_value=groups):
            stream = StringIO()
            with redirect_stdout(stream):
                MOD.inspect()
            self.assertIn("KODI_ORDER_MATCH=NO", stream.getvalue())

    def test_all_channels_not_counted_as_desired(self):
        tags = [{"name": "A"}]
        groups = [{"label": "All channels"}]
        with patch.object(MOD, "get_m3u_groups", return_value=["A"]), \
             patch.object(MOD, "get_tvh_tags", return_value=tags), \
             patch.object(MOD, "get_kodi_groups", return_value=groups):
            stream = StringIO()
            with redirect_stdout(stream):
                MOD.inspect()
            self.assertIn("KODI_M3U_GROUPS_MISSING=1", stream.getvalue())
