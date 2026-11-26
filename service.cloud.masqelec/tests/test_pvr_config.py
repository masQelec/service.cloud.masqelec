import json
import unittest

from unittest.mock import Mock

from lib import pvr_config as config


UUID = "1" * 32
EXTERNAL = "2" * 32


class NativeConfigTests(unittest.TestCase):

    def setUp(self):

        self.general = {
            "http_user_agent": "old",
        }

        self.epg = {
            "channel_rename": True,
            "channel_renumber": False,
            "channel_reicon": False,
        }

        self.internal = {
            "path": "/bin/tv_grab_file",
            "enabled": False,
            "scrape_extra": False,
        }

        self.external = {
            "path": "xmltv.sock",
            "enabled": False,
            "scrape_extra": False,
        }

        self.modules = [UUID, EXTERNAL]

        self.api_get = Mock(
            side_effect=self.get
        )

        self.api_post = Mock(
            side_effect=self.post
        )

    def get(self, endpoint, query=None, **kwargs):

        if endpoint == "epggrab/module/list":

            return True, 200, {
                "entries": [
                    {"uuid": uuid}
                    for uuid in self.modules
                ],
            }, ""

        if endpoint == "config/load":

            values = self.general
            node = {"class": "config"}

        elif endpoint == "epggrab/config/load":

            values = self.epg
            node = {"class": "epggrab"}

        elif endpoint == "idnode/load":

            uuid = query["uuid"]

            if uuid == UUID:

                values = self.internal

                node = {
                    "uuid": uuid,
                    "class": config.XMLTV_CLASS,
                }

            else:

                values = self.external

                node = {
                    "uuid": uuid,
                    "class": "epggrab_mod_ext_xmltv",
                }

        else:
            raise AssertionError(endpoint)

        node["params"] = [
            {"id": key, "value": value}
            for key, value in values.items()
        ]

        return True, 200, {
            "entries": [node],
        }, ""

    def post(self, endpoint, form, **kwargs):

        payload = json.loads(form["node"])

        if endpoint == "config/save":
            self.general.update(payload)

        elif endpoint == "epggrab/config/save":
            self.epg.update(payload)

        elif endpoint == "idnode/save":

            uuid = payload.pop("uuid")

            self.assertEqual(uuid, UUID)

            self.internal.update(payload)

        else:
            raise AssertionError(endpoint)

        return True, 200, "{}"

    def ensure(self):

        return config.ensure_config(
            self.api_get,
            self.api_post,
            authorized=True,
        )

    def test_not_authorized(self):

        self.assertEqual(
            config.ensure_config(
                self.api_get,
                self.api_post,
            )["status"],
            "NOT_AUTHORIZED",
        )

        self.api_get.assert_not_called()
        self.api_post.assert_not_called()

    def test_native_configuration(self):

        self.assertEqual(
            self.ensure()["status"],
            "UPDATED",
        )

        self.assertEqual(
            self.general["http_user_agent"],
            config.USER_AGENT,
        )

        self.assertFalse(
            self.epg["channel_rename"]
        )

        self.assertTrue(
            self.internal["enabled"]
        )

        self.assertTrue(
            self.internal["scrape_extra"]
        )

        self.assertFalse(
            self.external["scrape_extra"]
        )

        self.assertEqual(
            self.api_post.call_count, 3
        )

    def test_idempotent(self):

        self.ensure()
        self.api_post.reset_mock()

        self.assertEqual(
            self.ensure()["status"],
            "UNCHANGED",
        )

        self.api_post.assert_not_called()

    def test_missing_module(self):

        self.modules = [EXTERNAL]

        with self.assertRaisesRegex(
            config.ConfigError,
            "XMLTV_MODULE_NOT_UNIQUE",
        ):
            self.ensure()

        self.api_post.assert_not_called()

    def test_missing_property(self):

        del self.internal["scrape_extra"]

        with self.assertRaises(
            config.ConfigError
        ):
            self.ensure()

        self.api_post.assert_not_called()

    def test_http_write_failure(self):

        self.api_post.side_effect = None

        self.api_post.return_value = (
            False, 403, ""
        )

        with self.assertRaisesRegex(
            config.ConfigError,
            "API_SAVE_FAILED",
        ):
            self.ensure()

    def test_readback_required(self):

        self.api_post.side_effect = None

        self.api_post.return_value = (
            True, 200, "{}"
        )

        with self.assertRaisesRegex(
            config.ConfigError,
            "CONFIG_WRITE_NOT_CONFIRMED",
        ):
            self.ensure()

    def test_only_owned_settings_written(self):

        self.ensure()

        written = [
            json.loads(
                call.args[1]["node"]
            )
            for call in self.api_post.call_args_list
        ]

        self.assertEqual(
            written,
            [
                {"http_user_agent": config.USER_AGENT},
                {"channel_rename": False},
                {
                    "uuid": UUID,
                    "enabled": True,
                    "scrape_extra": True,
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
