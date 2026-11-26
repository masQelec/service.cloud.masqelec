import unittest

from unittest.mock import Mock, call

from lib import pvr_epg_settings as epg


class EpgSettingsTests(unittest.TestCase):

    def setUp(self):

        self.settings = {
            "XMLTV_TYPE": "NONE",
            "XMLTV_LOCATION_WEB": "http://",
            "XMLTV_LOCATION_FILE": "/original.xml",
            "DEBUG_LOG": "false",
        }

        self.addon = Mock()

        self.addon.getSetting.side_effect = (
            self.settings.__getitem__
        )

        self.addon.setSetting.side_effect = (
            self.settings.__setitem__
        )

        self.factory = Mock(
            return_value=self.addon
        )

    def test_not_authorized(self):

        self.assertEqual(
            epg.ensure_settings(self.factory),
            "NOT_AUTHORIZED",
        )

        self.factory.assert_not_called()

    def test_read_only_inspection(self):

        result = epg.inspect_settings(self.factory)

        self.assertEqual(
            result["XMLTV_TYPE"], "NONE"
        )

        self.addon.setSetting.assert_not_called()

    def test_native_configuration(self):

        self.assertEqual(
            epg.ensure_settings(
                self.factory,
                authorized=True,
            ),
            "UPDATED",
        )

        self.assertEqual(
            self.addon.setSetting.call_args_list,
            [
                call("XMLTV_LOCATION_WEB", epg.EPG_URL),
                call("XMLTV_TYPE", "WEB"),
            ],
        )

        self.assertEqual(
            self.settings["XMLTV_LOCATION_FILE"],
            "/original.xml",
        )

        self.assertEqual(
            self.settings["DEBUG_LOG"],
            "false",
        )

    def test_idempotent_configuration(self):

        self.settings.update(
            dict(epg.DESIRED_SETTINGS)
        )

        self.assertEqual(
            epg.ensure_settings(
                self.factory,
                authorized=True,
            ),
            "UNCHANGED",
        )

        self.addon.setSetting.assert_not_called()

    def test_only_changed_setting_written(self):

        self.settings["XMLTV_LOCATION_WEB"] = epg.EPG_URL

        self.assertEqual(
            epg.ensure_settings(
                self.factory,
                authorized=True,
            ),
            "UPDATED",
        )

        self.addon.setSetting.assert_called_once_with(
            "XMLTV_TYPE", "WEB"
        )

    def test_failed_url_write_blocks_type_change(self):

        self.addon.setSetting.side_effect = None

        with self.assertRaisesRegex(
            epg.EpgSettingsError,
            "XMLTV_SETTING_NOT_CONFIRMED",
        ):

            epg.ensure_settings(
                self.factory,
                authorized=True,
            )

        self.assertEqual(
            self.settings["XMLTV_TYPE"], "NONE"
        )

        self.addon.setSetting.assert_called_once_with(
            "XMLTV_LOCATION_WEB", epg.EPG_URL
        )


if __name__ == "__main__":
    unittest.main()
