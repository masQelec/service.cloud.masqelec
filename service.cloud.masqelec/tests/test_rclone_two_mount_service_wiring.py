# -*- coding: utf-8 -*-
"""Production Kodi service wiring checks without importing xbmc."""
from pathlib import Path
import unittest


class V2ServiceWiringTests(unittest.TestCase):
    def test_hourly_oauth_worker_uses_real_device_role_provider(self):
        text = (Path(__file__).resolve().parents[1] / "service.py").read_text()
        self.assertIn("from lib import device_utils", text)
        self.assertIn("role = device_utils.get_device_role()", text)
        self.assertNotIn("        role = utils.get_device_role()\n", text)
        self.assertIn("rclone_two_mount_master_runtime.run_once(", text)
        self.assertIn("rclone_two_mount_client_worker.tick(", text)

    def test_general_cleanup_only_after_active_verified(self):
        text = (Path(__file__).resolve().parents[1] / "service.py").read_text()
        self.assertIn('if status in ("ACTIVE_VERIFIED_LEGACY_RETIRED",', text)
        self.assertIn('"ACTIVE_CLEAN_ALREADY"):', text)
        self.assertIn("split.retire_once(", text)
        self.assertIn("authorized=True, health_verified=True", text)


if __name__ == "__main__":
    unittest.main()
