# -*- coding: utf-8 -*-

import json
import unittest

from lib import tvheadend_kodi as kodi


class FakeKodi:

    def __init__(self):

        self.version = "21.2.7"
        self.enabled = True
        self.next_version = "21.2.8"

        self.calls = []
        self.builtins = []

        self.apply_enabled = True
        self.apply_rescan = True

    def rpc(self, raw):

        request = json.loads(raw)
        method = request["method"]

        self.calls.append(method)

        if method == "Addons.GetAddonDetails":

            result = {
                "addon": {
                    "addonid": kodi.ADDON_ID,
                    "version": self.version,
                    "enabled": self.enabled,
                },
            }

        elif method == "Addons.SetAddonEnabled":

            if self.apply_enabled:
                self.enabled = request[
                    "params"
                ]["enabled"]

            result = "OK"

        else:
            raise AssertionError(
                "Unexpected RPC"
            )

        return json.dumps({
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": result,
        })

    def builtin(self, command, wait):

        self.builtins.append(
            (command, wait)
        )

        if command != "UpdateLocalAddons":
            raise AssertionError(
                "Unexpected builtin"
            )

        if self.apply_rescan:
            self.version = self.next_version


class TvheadendKodiTests(unittest.TestCase):

    def setUp(self):

        self.fake = FakeKodi()

        self.controller = kodi.KodiController(
            self.fake.rpc,
            self.fake.builtin,
            wait=lambda seconds: False,
        )

    def test_read_installed_state(self):

        self.assertEqual(
            self.controller.state(),
            kodi.AddonState("21.2.7", True),
        )

    def test_disable_confirmed(self):

        state = self.controller.set_enabled(
            False, "21.2.7"
        )

        self.assertFalse(state.enabled)
        self.assertFalse(self.fake.enabled)

    def test_enable_confirmed(self):

        self.fake.enabled = False

        state = self.controller.set_enabled(
            True, "21.2.7"
        )

        self.assertTrue(state.enabled)

    def test_no_redundant_enable(self):

        self.controller.set_enabled(
            True, "21.2.7"
        )

        self.assertNotIn(
            "Addons.SetAddonEnabled",
            self.fake.calls,
        )

    def test_unexpected_version_blocks(self):

        with self.assertRaisesRegex(
            kodi.KodiAddonError,
            "^KODI_VERSION_CHANGED$",
        ):

            self.controller.set_enabled(
                False, "21.2.8"
            )

        self.assertTrue(self.fake.enabled)

    def test_ack_without_state_change(self):

        self.fake.apply_enabled = False

        with self.assertRaisesRegex(
            kodi.KodiAddonError,
            "^KODI_STATE_NOT_CONFIRMED$",
        ):

            self.controller.set_enabled(
                False, "21.2.7"
            )

    def test_rescan_requires_disabled_addon(self):

        with self.assertRaisesRegex(
            kodi.KodiAddonError,
            "^KODI_ADDON_MUST_BE_DISABLED$",
        ):

            self.controller.rescan_disabled(
                "21.2.8"
            )

        self.assertEqual(
            self.fake.builtins, []
        )

    def test_rescan_detects_new_version(self):

        self.fake.enabled = False

        state = self.controller.rescan_disabled(
            "21.2.8"
        )

        self.assertEqual(
            state,
            kodi.AddonState("21.2.8", False),
        )

        self.assertEqual(
            self.fake.builtins,
            [("UpdateLocalAddons", True)],
        )

    def test_rescan_version_not_updated(self):

        self.fake.enabled = False
        self.fake.apply_rescan = False

        with self.assertRaisesRegex(
            kodi.KodiAddonError,
            "^KODI_STATE_NOT_CONFIRMED$",
        ):

            self.controller.rescan_disabled(
                "21.2.8"
            )

    def test_invalid_rpc_responses(self):

        for raw in (
            "{}",
            "",
            "invalid",
            '{"jsonrpc":"2.0","id":true,"result":{}}',
            '{"jsonrpc":"2.0","id":1,"error":{}}',
            '{"jsonrpc":"2.0","id":1}',
        ):

            controller = kodi.KodiController(
                lambda request: raw,
                self.fake.builtin,
            )

            with self.assertRaises(
                kodi.KodiAddonError
            ):

                controller.state()

    def test_abort_during_wait(self):

        controller = kodi.KodiController(
            self.fake.rpc,
            self.fake.builtin,
            wait=lambda seconds: True,
        )

        with self.assertRaisesRegex(
            kodi.KodiAddonError,
            "^KODI_WAIT_ABORTED$",
        ):

            controller.wait_state(
                "21.2.8", False
            )

    def test_complete_update_lifecycle(self):

        self.controller.set_enabled(
            False, "21.2.7"
        )

        self.controller.rescan_disabled(
            "21.2.8"
        )

        result = self.controller.set_enabled(
            True, "21.2.8"
        )

        self.assertEqual(
            result,
            kodi.AddonState("21.2.8", True),
        )

    def test_rescan_back_to_previous_version(self):

        self.fake.enabled = False
        self.fake.version = "21.2.8"
        self.fake.next_version = "21.2.7"

        result = self.controller.rescan_disabled(
            "21.2.7"
        )

        self.assertEqual(
            result,
            kodi.AddonState("21.2.7", False),
        )


if __name__ == "__main__":
    unittest.main()
