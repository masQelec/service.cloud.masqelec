# -*- coding: utf-8 -*-
"""Comparacion de versiones y decision de actualizacion."""

import json
import tempfile
import unittest

from pathlib import Path

from lib import tvheadend_version as version
from lib import tvheadend_manifest as manifest
from lib import tvheadend_platform as platform

from test_tvheadend_platform import MASTER
from test_tvheadend_manifest import CANDIDATE


class TvheadendVersionTests(unittest.TestCase):

    def setUp(self):

        self.device = platform.detect_from_text(
            MASTER
        )

        self.data = json.loads(
            CANDIDATE.read_text(encoding="utf-8")
        )

    def distribution(self, authorized=True):

        if authorized:
            self.data["packages"][0][
                "validated_builds"
            ] = [{
                "version_id": (
                    self.device.coreelec_version
                ),
                "build": self.device.coreelec_build,
            }]

        return manifest.parse_manifest(
            json.dumps(self.data).encode("utf-8"),
            21,
        )

    def decide(self, installed):

        return version.decide_update(
            self.distribution(),
            self.device,
            installed,
        )

    def test_master_update_available(self):

        result = self.decide("21.2.7")

        self.assertEqual(
            result.status,
            version.UPDATE_AVAILABLE,
        )

        self.assertEqual(
            result.available_version, "21.2.8"
        )

        self.assertEqual(
            result.package.target,
            "Amlogic-ng.arm",
        )

    def test_same_version_no_update(self):

        self.assertEqual(
            self.decide("21.2.8").status,
            version.UP_TO_DATE,
        )

    def test_newer_local_no_downgrade(self):

        self.assertEqual(
            self.decide("21.2.9").status,
            version.LOCAL_NEWER,
        )

    def test_numeric_not_alphabetic(self):

        self.assertEqual(
            version.compare_versions(
                "21.2.10", "21.2.9"
            ),
            1,
        )

        self.assertEqual(
            version.compare_versions(
                "21.2.9", "21.2.10"
            ),
            -1,
        )

    def test_four_component_installed_version(self):

        self.assertEqual(
            self.decide("21.2.8.1").status,
            version.LOCAL_NEWER,
        )

        self.assertEqual(
            self.decide("21.2.8.0").status,
            version.UP_TO_DATE,
        )

        self.assertEqual(
            self.decide("21.2.7.9").status,
            version.UPDATE_AVAILABLE,
        )

    def test_invalid_versions_blocked(self):

        for value in (
            None, True, "", "unknown",
            "21", "21.2", "21.2.8-beta",
            "021.2.8", "21.2.-8",
            "21.2.8.1.1", " 21.2.8",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(
                    version.VersionError,
                    "^INVALID_VERSION$",
                ):
                    self.decide(value)

    def test_unvalidated_build_blocks_update(self):

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^COREELEC_BUILD_NOT_VALIDATED$",
        ):
            version.decide_update(
                self.distribution(
                    authorized=False
                ),
                self.device,
                "21.2.7",
            )

    def test_read_installed_addon_version(self):

        with tempfile.TemporaryDirectory() as tmp:

            path = Path(tmp) / "addon.xml"

            path.write_bytes(
                b'<?xml version="1.0"?>'
                b'<addon id="service.tvheadend43" '
                b'version="21.2.7"/>'
            )

            self.assertEqual(
                version.read_installed_version(path),
                "21.2.7",
            )

    def test_missing_installed_addon(self):

        with tempfile.TemporaryDirectory() as tmp:

            with self.assertRaisesRegex(
                version.VersionError,
                "^ADDON_NOT_INSTALLED$",
            ):
                version.read_installed_version(
                    Path(tmp) / "addon.xml"
                )

    def test_invalid_addon_metadata(self):

        cases = (
            (
                b"<addon>",
                "INVALID_ADDON_XML",
            ),
            (
                b'<addon id="service.other" '
                b'version="21.2.7"/>',
                "WRONG_INSTALLED_ADDON",
            ),
            (
                b'<addon id="service.tvheadend43"/>',
                "INVALID_VERSION",
            ),
            (
                b'<addon id="service.tvheadend43" '
                b'version="unknown"/>',
                "INVALID_VERSION",
            ),
            (
                b"\xff\xfe",
                "INVALID_ADDON_XML",
            ),
        )

        for raw, error in cases:

            with self.subTest(error=error):

                with self.assertRaisesRegex(
                    version.VersionError,
                    "^" + error + "$",
                ):
                    version.parse_installed_addon_xml(
                        raw
                    )

    def test_oversized_addon_xml(self):

        with self.assertRaisesRegex(
            version.VersionError,
            "^INVALID_ADDON_XML_SIZE$",
        ):
            version.parse_installed_addon_xml(
                b"A" * (
                    version.MAX_ADDON_XML_BYTES + 1
                )
            )

    def test_xml_entities_rejected(self):

        raw = (
            b'<!DOCTYPE addon ['
            b'<!ENTITY value "21.2.7">'
            b']>'
            b'<addon id="service.tvheadend43" '
            b'version="&value;"/>'
        )

        with self.assertRaisesRegex(
            version.VersionError,
            "^UNSAFE_ADDON_XML$",
        ):
            version.parse_installed_addon_xml(raw)


if __name__ == "__main__":
    unittest.main()
