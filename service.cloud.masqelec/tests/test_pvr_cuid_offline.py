"""G3-AA CUID comparison offline unit tests."""
import importlib.util
from pathlib import Path
import unittest

p = Path(__file__).resolve().parents[1] / "lib" / "pvr_cuid_offline.py"
spec = importlib.util.spec_from_file_location("pvr_cuid_offline", p)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def make(rows):
    lines = ["#EXTM3U"]
    for cuid, name, group, url in rows:
        lines += ['#EXTINF:-1 CUID="%s" tvg-chno="1" tvg-name="%s" '
                  'group-title="%s",%s' % (cuid, name, group, name), url]
    return "\n".join(lines) + "\n"


BASE = [("1", "A", "News", "http://streams/ch1.ts"),
        ("2", "B", "Sports", "http://streams/ch2.ts")]


class CuidOfflineTests(unittest.TestCase):
    def test_no_change(self):
        r = m.compare(m.parse(make(BASE)), m.parse(make(BASE)))
        self.assertEqual((r["retained_cuids"], r["added_cuids"], r["removed_cuids"]), (2, 0, 0))
        self.assertEqual(r["renamed"], 0)

    def test_rename_keeps_identity(self):
        changed = [("1", "New name", "News", BASE[0][3]), BASE[1]]
        r = m.compare(m.parse(make(BASE)), m.parse(make(changed)))
        self.assertEqual((r["renamed"], r["retained_cuids"]), (1, 2))

    def test_url_change(self):
        changed = [("1", "A", "News", "https://streams/other.ts"), BASE[1]]
        self.assertEqual(m.compare(m.parse(make(BASE)), m.parse(make(changed)))["url_changed"], 1)

    def test_group_change(self):
        changed = [("1", "A", "New Group", BASE[0][3]), BASE[1]]
        self.assertEqual(m.compare(m.parse(make(BASE)), m.parse(make(changed)))["group_changed"], 1)

    def test_order_change(self):
        r = m.compare(m.parse(make(BASE)), m.parse(make(list(reversed(BASE)))))
        self.assertEqual(r["position_changed"], 2)

    def test_same_name_distinct_cuids(self):
        changed = [("1", "Same", "News", BASE[0][3]),
                   ("2", "Same", "Sports", BASE[1][3])]
        r = m.compare(m.parse(make(BASE)), m.parse(make(changed)))
        self.assertEqual(r["ambiguous_names_after"], 2)
        self.assertEqual(r["retained_cuids"], 2)

    def test_add_remove(self):
        changed = [BASE[0], ("3", "C", "News", "http://streams/ch3.ts")]
        r = m.compare(m.parse(make(BASE)), m.parse(make(changed)))
        self.assertEqual((r["added_cuids"], r["removed_cuids"]), (1, 1))

    def test_duplicate_cuid_denied(self):
        with self.assertRaisesRegex(m.Blocked, "DUPLICATE_CUID"):
            m.parse(make([BASE[0], ("1", "B", "Other", "http://streams/ch2.ts")]))

    def test_missing_cuid_denied(self):
        with self.assertRaisesRegex(m.Blocked, "ATTRIBUTE_MISSING_OR_DUPLICATE"):
            m.parse(make(BASE).replace('CUID="1" ', ""))

    def test_missing_stream_denied(self):
        with self.assertRaisesRegex(m.Blocked, "MISSING_STREAM_URL"):
            m.parse('#EXTM3U\n#EXTINF:-1 CUID="1" tvg-name="A" group-title="G",A\n')

    def test_invalid_header_denied(self):
        with self.assertRaisesRegex(m.Blocked, "MISSING_M3U_HEADER"):
            m.parse(make(BASE).replace("#EXTM3U", "#EXTX", 1))

    def test_no_mutation_claim(self):
        r = m.compare(m.parse(make(BASE)), m.parse(make(BASE)))
        for k in ("tvh_preserves_cuid_proven", "kodi_preserves_cuid_proven", "delete_authorized"):
            self.assertFalse(r[k])

    def test_no_url_or_cuid_values_in_result(self):
        r = m.compare(m.parse(make(BASE)), m.parse(make(BASE)))
        self.assertNotIn("http://streams/", str(r))
        self.assertNotIn("Sports", str(r))

    def test_missing_name_denied(self):
        with self.assertRaisesRegex(m.Blocked, "INVALID_NAME_OR_GROUP"):
            m.parse(make(BASE).replace('tvg-name="A"', 'tvg-name=""'))

    def test_zero_channels_denied(self):
        with self.assertRaisesRegex(m.Blocked, "EMPTY_PLAYLIST"):
            m.parse("#EXTM3U\n")


if __name__ == "__main__":
    unittest.main()
