"""G3-AB stage fixture tests without TVH, Kodi or production writes."""
import importlib.util
from pathlib import Path
import unittest
from unittest import mock
import tempfile

p = Path(__file__).resolve().parents[1] / "lab" / "pvr_g3ab" / "prepare.py"
spec = importlib.util.spec_from_file_location("pvr_g3ab_prepare", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


class FixtureTests(unittest.TestCase):
    def test_all_stages_keep_cuids(self):
        expected = set(m.CUIDS)
        for stage in m.STAGES:
            with self.subTest(stage=stage):
                self.assertEqual(set(x["cuid"] for x in m.entries(stage)), expected)

    def test_unique_cuids(self):
        for stage in m.STAGES:
            ids = [x["cuid"] for x in m.entries(stage)]
            self.assertEqual(len(ids), len(set(ids)))

    def test_baseline_two_channels(self):
        self.assertEqual(len(m.entries("baseline")), 2)

    def test_rename_only_name(self):
        before, after = m.entries("baseline"), m.entries("rename")
        self.assertEqual(before[0]["cuid"], after[0]["cuid"])
        self.assertEqual({k:v for k,v in before[0].items() if k!="name"},
                         {k:v for k,v in after[0].items() if k!="name"})
        self.assertNotEqual(before[0]["name"], after[0]["name"])

    def test_url_only_url(self):
        a, b = m.entries("baseline")[0], m.entries("url")[0]
        self.assertEqual({k:v for k,v in a.items() if k!="url"},
                         {k:v for k,v in b.items() if k!="url"})
        self.assertNotEqual(a["url"], b["url"])

    def test_group_only_group(self):
        a, b = m.entries("baseline")[0], m.entries("group")[0]
        self.assertEqual({k:v for k,v in a.items() if k!="group"},
                         {k:v for k,v in b.items() if k!="group"})
        self.assertNotEqual(a["group"], b["group"])

    def test_reorder_only_order(self):
        self.assertEqual(m.entries("reorder"), list(reversed(m.entries("baseline"))))

    def test_homonym_different_cuids(self):
        rows = m.entries("homonym")
        self.assertEqual(rows[0]["name"], rows[1]["name"])
        self.assertNotEqual(rows[0]["cuid"], rows[1]["cuid"])

    def test_restore_equal_baseline(self):
        self.assertEqual(m.playlist("restored"), m.playlist("baseline"))

    def test_quoted_cuid_in_playlist(self):
        text = m.playlist("baseline")
        for cuid in m.CUIDS:
            self.assertIn('CUID="' + cuid + '"', text)

    def test_only_synthetic_stream_host(self):
        for stage in m.STAGES:
            self.assertEqual(len(m.playlist(stage).split("#EXTINF:")) - 1, 2)
            for row in m.entries(stage):
                self.assertTrue(row["url"].startswith("http://streams/ch"))

    def test_invalid_stage_rejected(self):
        with self.assertRaises(ValueError):
            m.entries("production")

    def test_atomic_write(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "playlist.m3u"
            m.atomic_write(target, "synthetic")
            self.assertEqual(target.read_text(), "synthetic")

    def test_symlink_playlist_denied(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)
            (path / "real").write_text("safe")
            (path / "playlist.m3u").symlink_to("real")
            with self.assertRaisesRegex(RuntimeError, "PLAYLIST_SYMLINK_DENIED"):
                m.atomic_write(path / "playlist.m3u", "bad")
            self.assertEqual((path / "real").read_text(), "safe")

    def test_preflight_marked_and_sandboxed(self):
        with tempfile.TemporaryDirectory() as root:
            lab = Path(root) / "g3ab"
            lab.mkdir()
            with mock.patch.object(m, "ROOT", lab), mock.patch.object(m, "RUNTIME", lab / "runtime"), mock.patch.object(m, "GUARD", lab / "runtime" / ".g3ab-synthetic-only"):
                m.preflight()
                self.assertTrue((lab / "runtime" / ".g3ab-synthetic-only").is_file())
                for folder in m.DIRS:
                    self.assertTrue((lab / "runtime" / folder).is_dir())

    def test_invalid_marker_denied(self):
        with tempfile.TemporaryDirectory() as root:
            lab = Path(root)
            runtime = lab / "runtime"
            runtime.mkdir()
            guard = runtime / ".g3ab-synthetic-only"
            guard.write_text("bad\n")
            with mock.patch.object(m,"ROOT",lab),mock.patch.object(m,"RUNTIME",runtime),mock.patch.object(m,"GUARD",guard):
                with self.assertRaisesRegex(RuntimeError,"INVALID_LAB_MARKER"):
                    m.preflight()


if __name__ == "__main__":
    unittest.main()
