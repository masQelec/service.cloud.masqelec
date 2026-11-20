"""No-network synthetic tests for G1 metadata-only M3U parsing."""
import importlib.util
from pathlib import Path
import unittest

PATH = Path(__file__).resolve().parents[1] / "lib" / "pvr_playlist_metadata.py"
spec = importlib.util.spec_from_file_location("pvr_playlist_metadata", PATH)
import sys
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)


def m3u(*records):
    lines = ["#EXTM3U"]
    for cuid, number, name, group in records:
        lines += [
            '#EXTINF:-1 CUID="%s" tvh-chnum="%s" tvg-chno="%s" group-title="%s",%s' %
            (cuid, number, number, group, name),
            "https://user:private@invalid.example/stream"]
    return ("\n".join(lines) + "\n").encode()


class PvrPlaylistG1Tests(unittest.TestCase):
    def test_valid_reorder_and_rename(self):
        old = module.parse_metadata(m3u((12, 1, "News", "A"), (42, 2, "Drama", "B")))
        new = module.parse_metadata(m3u((42, 1, "Drama HD", "A"), (12, 2, "News", "B")))
        result = module.diff_same_generation(old, new, generation_verified=True)
        self.assertEqual(result["changed"], ["12", "42"])
        self.assertEqual(result["removed_candidates"], [])
        self.assertFalse(result["destructive_operations_authorized"])

    def test_new_and_removed_stay_candidates_only(self):
        old = module.parse_metadata(m3u((12, 1, "News", "A")))
        new = module.parse_metadata(m3u((42, 1, "News", "A")))
        with self.assertRaisesRegex(module.PlaylistInvalid, "generation"):
            module.diff_same_generation(old, new)
        result = module.diff_same_generation(old, new, generation_verified=True)
        self.assertEqual(result["removed_candidates"], ["12"])
        self.assertFalse(result["destructive_operations_authorized"])

    def test_duplicate_names_are_legal(self):
        self.assertEqual(len(module.parse_metadata(
            m3u((12, 1, "Same", "A"), (42, 2, "Same", "A")))), 2)

    def test_duplicate_cuid_denied(self):
        with self.assertRaises(module.PlaylistInvalid):
            module.parse_metadata(m3u((12, 1, "A", "G"), (12, 2, "B", "G")))

    def test_duplicate_number_denied(self):
        with self.assertRaises(module.PlaylistInvalid):
            module.parse_metadata(m3u((12, 1, "A", "G"), (13, 1, "B", "G")))

    def test_truncated_m3u_denied(self):
        with self.assertRaises(module.PlaylistInvalid):
            module.parse_metadata(b'#EXTM3U\n#EXTINF:-1 CUID="1",A\n')

    def test_wrong_header_denied(self):
        with self.assertRaises(module.PlaylistInvalid):
            module.parse_metadata(b'<html>invalid</html>')

    def test_unmatched_channel_numbers_denied(self):
        data = m3u((12, 1, "A", "G")).replace(b'tvg-chno="1"', b'tvg-chno="2"')
        with self.assertRaises(module.PlaylistInvalid):
            module.parse_metadata(data)

    def test_never_return_stream_url(self):
        result = module.parse_metadata(m3u((12, 1, "A", "G")))
        self.assertNotIn("private", repr(result))
        self.assertNotIn("invalid.example", repr(result))


if __name__ == "__main__":
    unittest.main()
