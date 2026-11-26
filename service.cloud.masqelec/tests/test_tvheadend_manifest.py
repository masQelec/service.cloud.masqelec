# -*- coding: utf-8 -*-
"""Validacion del manifiesto Tvheadend sin red."""

import copy
import json
import unittest

from pathlib import Path

from lib import tvheadend_manifest as manifest
from lib import tvheadend_platform as platform

from test_tvheadend_platform import MASTER, NE


ROOT = Path(__file__).resolve().parents[1]

CANDIDATE = (
    ROOT / "docs/"
    "PVR_03_TVHEADEND_MANIFEST_CANDIDATE.json"
)


class TvheadendManifestTests(unittest.TestCase):

    def setUp(self):
        self.data = json.loads(
            CANDIDATE.read_text(encoding="utf-8")
        )

        self.ng = platform.detect_from_text(MASTER)
        self.ne = platform.detect_from_text(NE)

    def parse(self, data=None, major=21):
        return manifest.parse_manifest(
            json.dumps(
                self.data if data is None else data
            ).encode("utf-8"),
            major,
        )

    def authorize(self, index, device):
        self.data["packages"][index][
            "validated_builds"
        ].append({
            "version_id": device.coreelec_version,
            "build": device.coreelec_build,
        })

    def test_real_candidate_manifest(self):
        result = self.parse()

        self.assertEqual(result.kodi_major, 21)
        self.assertEqual(len(result.packages), 2)

        self.assertEqual(
            result.packages[0].size,
            32654890
        )

        self.assertEqual(
            result.packages[1].size,
            34641758
        )

    def test_candidates_cannot_be_installed(self):
        result = self.parse()

        for device in (self.ng, self.ne):
            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^COREELEC_BUILD_NOT_VALIDATED$"
            ):
                manifest.select_package(result, device)

    def test_ng_selection(self):
        self.authorize(0, self.ng)

        package = manifest.select_package(
            self.parse(), self.ng
        )

        self.assertEqual(
            package.target, "Amlogic-ng.arm"
        )

        self.assertEqual(package.version, "21.2.8")

    def test_ne_selection(self):
        self.authorize(1, self.ne)

        package = manifest.select_package(
            self.parse(), self.ne
        )

        self.assertEqual(
            package.target, "Amlogic-ne.aarch64"
        )

    def test_no_architecture_fallback(self):
        self.authorize(1, self.ne)
        self.data["packages"].pop(0)

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^NO_COMPATIBLE_TARGET$"
        ):
            manifest.select_package(
                self.parse(), self.ng
            )

    def test_different_build_not_authorized(self):
        self.authorize(0, self.ng)

        other = platform.detect_from_text(
            MASTER.replace(
                "20250919152246",
                "20261001000000"
            )
        )

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^COREELEC_BUILD_NOT_VALIDATED$"
        ):
            manifest.select_package(
                self.parse(), other
            )

    def test_wrong_kodi_major(self):
        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^KODI_MAJOR_MISMATCH$"
        ):
            self.parse(major=22)

    def test_wrong_addon_id(self):
        self.data["addon_id"] = "service.other"

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^WRONG_ADDON_ID$"
        ):
            self.parse()

    def test_invalid_schema(self):
        for schema in (True, 2, "1"):
            self.data["schema"] = schema

            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^UNSUPPORTED_MANIFEST_SCHEMA$"
            ):
                self.parse()

    def test_invalid_package_path(self):
        for path in (
            "../other.zip",
            "https://example.com/package.zip",
            "/storage/package.zip",
            "pvr/tvheadend/other.zip",
        ):
            self.data["packages"][0]["path"] = path

            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^INVALID_PACKAGE_PATH$"
            ):
                self.parse()

    def test_invalid_sha256(self):
        for sha in ("", "a" * 63, "z" * 64):
            self.data["packages"][0]["sha256"] = sha

            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^INVALID_PACKAGE_SHA256$"
            ):
                self.parse()

    def test_invalid_size(self):
        for size in (
            True, -1, 0, "100",
            manifest.MAX_PACKAGE_BYTES + 1
        ):
            self.data["packages"][0]["size"] = size

            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^INVALID_PACKAGE_SIZE$"
            ):
                self.parse()

    def test_invalid_version(self):
        for version in (
            "21.2", "21.2.8-beta",
            "../21.2.8", True
        ):
            self.data["packages"][0][
                "version"
            ] = version

            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^INVALID_ADDON_VERSION$"
            ):
                self.parse()

    def test_duplicate_target(self):
        self.data["packages"][1] = copy.deepcopy(
            self.data["packages"][0]
        )

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^DUPLICATE_PACKAGE_TARGET$"
        ):
            self.parse()

    def test_duplicate_json_key(self):
        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^DUPLICATE_JSON_KEY$"
        ):
            manifest.parse_manifest(
                b'{"schema":1,"schema":2}', 21
            )

    def test_duplicate_compatibility_entry(self):
        self.authorize(0, self.ng)
        self.authorize(0, self.ng)

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^DUPLICATE_COMPATIBILITY_ENTRY$"
        ):
            self.parse()

    def test_oversized_manifest(self):
        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^INVALID_MANIFEST_SIZE$"
        ):
            manifest.parse_manifest(
                b"A" * (
                    manifest.MAX_MANIFEST_BYTES + 1
                ),
                21
            )

    def test_malformed_json(self):
        for raw in (
            b"invalid",
            b"\xff\xfe",
            b'{"schema":'
        ):
            with self.assertRaisesRegex(
                manifest.ManifestError,
                "^INVALID_MANIFEST_JSON$"
            ):
                manifest.parse_manifest(raw, 21)


if __name__ == "__main__":
    unittest.main()
