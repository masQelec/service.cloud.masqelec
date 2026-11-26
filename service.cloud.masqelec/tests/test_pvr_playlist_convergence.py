import tempfile
import unittest

from pathlib import Path

from lib import pvr_playlist_convergence as convergence


class PlaylistConvergenceTests(unittest.TestCase):

    def setUp(self):

        temp = tempfile.TemporaryDirectory()

        self.addCleanup(temp.cleanup)

        self.playlist = Path(temp.name) / "playlist.m3u"

        self.urls = [
            "http://iptv.invalid/live/example/100",
            "http://iptv.invalid/live/example/200",
        ]

        self.playlist.write_text(
            "#EXTM3U\n"
            "#EXTINF:-1,Alpha\n" + self.urls[0] + "\n"
            "#EXTINF:-1,Beta\n" + self.urls[1] + "\n"
        )

        self.network = "a" * 32

        self.networks = [{
            "uuid": self.network,
            "url": convergence.PLAYLIST_URL,
            "num_mux": 2,
        }]

        self.muxes = [
            {
                "uuid": f"{i+1:032x}",
                "network_uuid": self.network,
                "iptv_url": url,
            }
            for i, url in enumerate(self.urls)
        ]

        self.calls = []

    def api(self, endpoint, query, timeout_s):

        self.calls.append(endpoint)

        entries = (
            self.networks
            if endpoint == "mpegts/network/grid"
            else self.muxes
        )

        return True, 200, {
            "total": len(entries),
            "entries": entries,
        }, ""

    def check(self):

        return convergence.check(
            self.api, self.playlist
        )

    def test_exact_match(self):

        self.assertEqual(
            self.check(), convergence.CONVERGED
        )

    def test_old_playlist_same_number_of_muxes(self):

        self.muxes[0]["iptv_url"] = (
            "http://iptv.invalid/old/999"
        )

        self.assertEqual(
            self.check(), convergence.DEFERRED
        )

    def test_missing_mux(self):

        self.muxes.pop()

        self.assertEqual(
            self.check(), convergence.DEFERRED
        )

    def test_extra_mux(self):

        self.muxes.append({
            "uuid": "b" * 32,
            "network_uuid": self.network,
            "iptv_url": "http://iptv.invalid/extra",
        })

        self.assertEqual(
            self.check(), convergence.DEFERRED
        )

    def test_duplicate_mux_identity(self):

        self.muxes[1]["uuid"] = self.muxes[0]["uuid"]

        self.assertEqual(
            self.check(), convergence.UNKNOWN
        )

    def test_other_network_is_ignored(self):

        self.muxes.append({
            "uuid": "c" * 32,
            "network_uuid": "d" * 32,
            "iptv_url": "http://iptv.invalid/other",
        })

        self.assertEqual(
            self.check(), convergence.CONVERGED
        )

    def test_wrong_network_source(self):

        self.networks[0]["url"] = "file:///other.m3u"

        self.assertEqual(
            self.check(), convergence.UNKNOWN
        )

    def test_network_still_refreshing(self):

        self.networks[0]["num_mux"] = 1

        self.assertEqual(
            self.check(), convergence.DEFERRED
        )

        self.assertEqual(
            self.calls, ["mpegts/network/grid"]
        )

    def test_api_unavailable(self):

        result = convergence.check(
            lambda *args, **kwargs: (
                False, 404, None, ""
            ),
            self.playlist,
        )

        self.assertEqual(result, convergence.UNKNOWN)

    def test_incomplete_grid(self):

        result = convergence.check(
            lambda *args, **kwargs: (
                True, 200,
                {"total": 10, "entries": []},
                "",
            ),
            self.playlist,
        )

        self.assertEqual(result, convergence.UNKNOWN)

    def test_playlist_changes_during_check(self):

        def api(endpoint, **kwargs):

            result = self.api(endpoint, **kwargs)

            if endpoint == "mpegts/mux/grid":

                with self.playlist.open("a") as stream:
                    stream.write("#changed\n")

            return result

        self.assertEqual(
            convergence.check(api, self.playlist),
            convergence.DEFERRED,
        )

    def test_empty_playlist(self):

        self.playlist.write_text("#EXTM3U\n")

        self.assertEqual(
            self.check(), convergence.UNKNOWN
        )

        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
