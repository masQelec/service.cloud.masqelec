# -*- coding: utf-8 -*-
"""Verifica staging en RAM y publicación atómica; no requiere Kodi."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import catalog_workspace as work


class CatalogWorkspaceTests(unittest.TestCase):
    def test_prefers_tmp_with_free_space(self):
        with tempfile.TemporaryDirectory() as root:
            ram = os.path.join(root, "ram")
            disk = os.path.join(root, "disk")
            os.mkdir(ram)
            with mock.patch.object(work.shutil, "disk_usage",
                                   return_value=SimpleNamespace(free=512 * 1024 * 1024)):
                self.assertEqual(work.select_staging_base(ram, disk), ram)

    def test_falls_back_when_tmp_is_small(self):
        with tempfile.TemporaryDirectory() as root:
            ram = os.path.join(root, "ram")
            disk = os.path.join(root, "disk")
            os.mkdir(ram)
            with mock.patch.object(work.shutil, "disk_usage",
                                   return_value=SimpleNamespace(free=5 * 1024 * 1024)):
                self.assertEqual(work.select_staging_base(ram, disk), disk)
                self.assertTrue(os.path.isdir(disk))

    def test_cross_filesystem_publish_uses_target_directory(self):
        with tempfile.TemporaryDirectory() as root:
            ram = os.path.join(root, "ram")
            disk = os.path.join(root, "disk")
            os.mkdir(ram)
            os.mkdir(disk)
            src = os.path.join(ram, "catalog.zip")
            dst = os.path.join(disk, "catalog.zip")
            with open(src, "wb") as f:
                f.write(b"new-data")
            with open(dst, "wb") as f:
                f.write(b"old-data")
            orig_replace = work.os.replace
            observed = []

            def guard_replace(temp, final):
                observed.append((temp, final))
                self.assertEqual(os.path.dirname(temp), disk)
                return orig_replace(temp, final)

            with mock.patch.object(work.os, "replace", side_effect=guard_replace):
                work.publish_file_atomic(src, dst)
            self.assertEqual(len(observed), 1)
            with open(dst, "rb") as f:
                self.assertEqual(f.read(), b"new-data")
            with open(src, "rb") as f:
                self.assertEqual(f.read(), b"new-data")

    def test_failed_copy_preserves_previous_destination(self):
        with tempfile.TemporaryDirectory() as root:
            src = os.path.join(root, "src.zip")
            dst = os.path.join(root, "dest.zip")
            with open(src, "wb") as f:
                f.write(b"new-data")
            with open(dst, "wb") as f:
                f.write(b"old-data")

            def truncated_copy(source, output, length):
                output.write(b"x")
                raise OSError("simulated disk full")

            with mock.patch.object(work.shutil, "copyfileobj", side_effect=truncated_copy):
                with self.assertRaises(OSError):
                    work.publish_file_atomic(src, dst)
            with open(dst, "rb") as f:
                self.assertEqual(f.read(), b"old-data")
            self.assertEqual(sorted(os.listdir(root)), ["dest.zip", "src.zip"])


if __name__ == "__main__":
    unittest.main()
