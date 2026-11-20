# -*- coding: utf-8 -*-
"""Pruebas independientes del runtime Kodi."""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import catalog_safety


class CatalogSafetyTests(unittest.TestCase):
    def test_manifest_matches_historical_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            os.makedirs(os.path.join(directory, "videos"))
            os.makedirs(os.path.join(directory, "tvshows"))
            with open(os.path.join(directory, "videos", "one.strm"), "wb") as f:
                f.write(b"a")
            with open(os.path.join(directory, "tvshows", "two.strm"), "wb") as f:
                f.write(b"b")
            digest, count = catalog_safety.compute_catalog_hash(directory)
            self.assertEqual(count, 2)
            self.assertEqual(catalog_safety.verify_staging(
                directory, "{}  strm_files=2  utc=2026-11-17T00:00:00Z".format(digest)), 2)
            with open(os.path.join(directory, "videos", "one.strm"), "wb") as f:
                f.write(b"broken")
            with self.assertRaisesRegex(ValueError, "Hash"):
                catalog_safety.verify_staging(directory, "{} strm_files=2".format(digest))
            with self.assertRaisesRegex(ValueError, "Cantidad"):
                catalog_safety.verify_staging(directory, "{} strm_files=3".format(digest))

    def test_zip_validation_rejects_bad_members(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "catalog.zip")
            with zipfile.ZipFile(target, "w") as zipfile_out:
                zipfile_out.writestr("videos/safe.strm", "https://example.invalid/video")
            self.assertEqual(catalog_safety.validate_catalog_zip(target), 1)
            for bad in ("../videos/bad.strm", "videos/../bad.strm", "/videos/abs.strm", "videos/bad.txt"):
                with zipfile.ZipFile(target, "w") as zipfile_out:
                    zipfile_out.writestr(bad, "bad")
                with self.subTest(bad=bad):
                    with self.assertRaisesRegex(ValueError, "Ruta"):
                        catalog_safety.validate_catalog_zip(target)

    def test_zip_rejects_duplicates_and_bombs(self):
        with tempfile.TemporaryDirectory() as directory:
            target = os.path.join(directory, "catalog.zip")
            with zipfile.ZipFile(target, "w") as z:
                z.writestr("videos/too_large.strm", "x" * (catalog_safety.MAX_STRM_SIZE + 1))
            with self.assertRaisesRegex(ValueError, "límites"):
                catalog_safety.validate_catalog_zip(target)
            with zipfile.ZipFile(target, "w") as z:
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", UserWarning)
                    z.writestr("videos/a.strm", "one")
                    z.writestr("videos/a.strm", "two")
            with self.assertRaisesRegex(ValueError, "duplicada"):
                catalog_safety.validate_catalog_zip(target)

    def test_mass_delete_fence(self):
        catalog_safety.validate_deletions(1000, 250)
        catalog_safety.validate_deletions(1000, 0)
        with self.assertRaisesRegex(ValueError, "masivo"):
            catalog_safety.validate_deletions(1000, 251)
        with self.assertRaisesRegex(ValueError, "masivo"):
            catalog_safety.validate_deletions(100, 26)


if __name__ == "__main__":
    unittest.main()
