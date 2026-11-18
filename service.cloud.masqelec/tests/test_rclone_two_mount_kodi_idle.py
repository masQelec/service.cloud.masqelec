# -*- coding: utf-8 -*-
"""Kodi JSON-RPC playback gate: pruebas sin dispositivo ni xbmc."""
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import rclone_two_mount_kodi_idle as idle


def reply(result):
    return json.dumps({"jsonrpc": "2.0", "id": 1, "result": result})


class KodiIdleTests(unittest.TestCase):
    def test_empty_players_allows_maintenance(self):
        self.assertTrue(idle.is_playback_idle(lambda r: reply([])))

    def test_video_playing_denied(self):
        self.assertFalse(idle.is_playback_idle(lambda r: reply([
            {"playerid": 1, "type": "video"}])))

    def test_audio_playing_denied(self):
        self.assertFalse(idle.is_playback_idle(lambda r: reply([
            {"playerid": 0, "type": "audio"}])))

    def test_rpc_must_invoke_expected_method(self):
        def rpc(payload):
            obj = json.loads(payload)
            self.assertEqual(obj["method"], "Player.GetActivePlayers")
            self.assertEqual(obj["id"], 1)
            return reply([])
        self.assertTrue(idle.is_playback_idle(rpc))

    def test_rpc_error_denied(self):
        self.assertFalse(idle.is_playback_idle(
            lambda r: json.dumps({"jsonrpc":"2.0", "id":1,
                                  "error":{"code":-1,"message":"failure"}})))

    def test_unknown_json_shape_denied(self):
        for bad in ("{}", "[]", "null", "", "{broken",
                    '{"jsonrpc":"2.0","id":1,"result":null}',
                    '{"jsonrpc":"2.0","id":true,"result":[]}',
                    '{"jsonrpc":"2.0","id":1,"result":[],"other":1}'):
            with self.subTest(bad=bad):
                self.assertFalse(idle.is_playback_idle(lambda r: bad))

    def test_no_rpc_denied(self):
        self.assertFalse(idle.is_playback_idle(None))

    def test_timeout_or_exception_denied(self):
        def crash(_):
            raise TimeoutError("Kodi busy")
        self.assertFalse(idle.is_playback_idle(crash))

    def test_oversized_response_denied(self):
        self.assertFalse(idle.is_playback_idle(lambda r: " " * 65537))


if __name__ == "__main__":
    unittest.main()
