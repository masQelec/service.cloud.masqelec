# -*- coding: utf-8 -*-
"""Pruebas de MASTER con filesystem temporal; no necesitan Kodi."""
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import catalog_safety, master_catalog_safety


def _write(root, rel, data):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as stream:
        stream.write(data)
    return path


def _read(root, rel):
    with open(os.path.join(root, *rel.split("/")), "rb") as stream:
        return stream.read()


class MasterCatalogSafetyTests(unittest.TestCase):
    def test_copies_before_deleting_and_preserves_non_strm(self):
        with tempfile.TemporaryDirectory() as base:
            live = os.path.join(base, "live")
            stage = os.path.join(base, "stage")
            backup = os.path.join(base, "backup")
            _write(live, "videos/keep.strm", b"same")
            _write(live, "videos/old.strm", b"obsolete")
            _write(live, "videos/poster.jpg", b"keep-this")
            _write(stage, "videos/keep.strm", b"same")
            _write(stage, "videos/new.strm", b"new")
            _write(stage, "tvshows/Series/Season 01/ep.strm", b"episode")
            copies, deletions = master_catalog_safety.apply_staged_catalog(stage, live, backup)
            self.assertEqual((copies, deletions), (2, 1))
            self.assertEqual(_read(live, "videos/keep.strm"), b"same")
            self.assertEqual(_read(live, "videos/new.strm"), b"new")
            self.assertEqual(_read(live, "tvshows/Series/Season 01/ep.strm"), b"episode")
            self.assertEqual(_read(live, "videos/poster.jpg"), b"keep-this")
            self.assertFalse(os.path.exists(os.path.join(live, "videos", "old.strm")))

    def test_rejects_category_disappearing(self):
        with tempfile.TemporaryDirectory() as base:
            live = os.path.join(base, "live")
            stage = os.path.join(base, "stage")
            _write(live, "videos/movie.strm", b"old movie")
            _write(live, "tvshows/show.strm", b"old show")
            _write(stage, "tvshows/show.strm", b"old show")
            with self.assertRaisesRegex(ValueError, "categoría videos vacía"):
                master_catalog_safety.apply_staged_catalog(stage, live, os.path.join(base, "backup"))
            self.assertEqual(_read(live, "videos/movie.strm"), b"old movie")

    def test_rejects_mass_delete_before_any_write(self):
        with tempfile.TemporaryDirectory() as base:
            live = os.path.join(base, "live")
            stage = os.path.join(base, "stage")
            for i in range(100):
                rel = "videos/item{:03d}.strm".format(i)
                _write(live, rel, str(i).encode())
                if i < 50:
                    _write(stage, rel, str(i).encode())
            with self.assertRaisesRegex(ValueError, "masivo"):
                master_catalog_safety.apply_staged_catalog(stage, live, os.path.join(base, "backup"))
            self.assertEqual(_read(live, "videos/item099.strm"), b"99")

    def test_rollback_after_second_copy_fails(self):
        with tempfile.TemporaryDirectory() as base:
            live = os.path.join(base, "live")
            stage = os.path.join(base, "stage")
            _write(live, "videos/one.strm", b"original")
            _write(stage, "videos/one.strm", b"updated")
            _write(stage, "videos/two.strm", b"new")
            real = master_catalog_safety._replace_from_stage
            calls = [0]

            def fail_second(src, dst):
                calls[0] += 1
                if calls[0] == 2:
                    raise OSError("simulated disk error")
                return real(src, dst)

            with mock.patch.object(master_catalog_safety, "_replace_from_stage",
                                   side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "rollback completado"):
                    master_catalog_safety.apply_staged_catalog(
                        stage, live, os.path.join(base, "backup"))
            self.assertEqual(_read(live, "videos/one.strm"), b"original")
            self.assertFalse(os.path.exists(os.path.join(live, "videos/two.strm")))

    def test_verified_zip_matches_manifest_and_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as base:
            root = os.path.join(base, "content")
            _write(root, "videos/one.strm", b"stream-one")
            _write(root, "tvshows/series/two.strm", b"stream-two")
            digest, count = catalog_safety.compute_catalog_hash(root)
            version = "{} strm_files={}".format(digest, count)
            archive = os.path.join(base, "catalog.zip")
            with zipfile.ZipFile(archive, "w") as z:
                z.write(os.path.join(root, "videos/one.strm"), "videos/one.strm")
                z.write(os.path.join(root, "tvshows/series/two.strm"),
                        "tvshows/series/two.strm")
            self.assertEqual(catalog_safety.verify_zip_manifest(archive, version), 2)
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("videos/one.strm", "tampered")
                z.writestr("tvshows/series/two.strm", "stream-two")
            with self.assertRaisesRegex(ValueError, "Hash"):
                catalog_safety.verify_zip_manifest(archive, version)


if __name__ == "__main__":
    unittest.main()
