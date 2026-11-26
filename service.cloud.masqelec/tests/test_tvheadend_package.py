# -*- coding: utf-8 -*-

import hashlib
import io
import json
import stat
import tempfile
import unittest
import warnings
import zipfile

from dataclasses import replace
from pathlib import Path

from lib import tvheadend_package as package
from lib import tvheadend_manifest as manifest
from lib import tvheadend_platform as platform
from lib import tvheadend_version as version

from test_tvheadend_platform import MASTER, NE
from test_tvheadend_manifest import CANDIDATE


BASE = (
    "https://raw.githubusercontent.com/"
    "masQelec/cloud.masqelec/21"
)

ROOT = manifest.ADDON_ID


class FakeResponse(io.BytesIO):

    def __init__(
        self, payload, url,
        headers=None, status=200
    ):

        super().__init__(payload)

        self.url = url
        self.status = status

        self.headers = (
            {"Content-Length": str(len(payload))}
            if headers is None else headers
        )

    def geturl(self):
        return self.url

    def getcode(self):
        return self.status


def make_zip(
    bits=32,
    machine=40,
    addon_version="21.2.8",
    addon_id=ROOT,
    extras=(),
    include_binary=True,
):

    payload = io.BytesIO()

    header = bytearray(64)
    header[:4] = b"\x7fELF"
    header[4] = 1 if bits == 32 else 2
    header[5] = 1
    header[6] = 1
    header[16:18] = (3).to_bytes(2, "little")
    header[18:20] = machine.to_bytes(2, "little")

    with zipfile.ZipFile(
        payload, "w", zipfile.ZIP_DEFLATED
    ) as archive:

        archive.writestr(
            ROOT + "/addon.xml",
            f'<addon id="{addon_id}" '
            f'version="{addon_version}"/>',
        )

        if include_binary:
            archive.writestr(
                ROOT + "/bin/tvheadend",
                header,
            )

        for name, content in extras:
            archive.writestr(name, content)

    return payload.getvalue()


class TvheadendPackageTests(unittest.TestCase):

    def setUp(self):

        self.ng = platform.detect_from_text(MASTER)
        self.ne = platform.detect_from_text(NE)

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.folder = Path(self.tmp.name)

        self.data = json.loads(
            CANDIDATE.read_text(encoding="utf-8")
        )

    def distribution(
        self, payload,
        index=0, authorized=True
    ):

        device = self.ng if index == 0 else self.ne

        entry = self.data["packages"][index]

        entry["size"] = len(payload)
        entry["sha256"] = (
            hashlib.sha256(payload).hexdigest()
        )

        entry["validated_builds"] = (
            [{
                "version_id": device.coreelec_version,
                "build": device.coreelec_build,
            }]
            if authorized else []
        )

        return manifest.parse_manifest(
            json.dumps(self.data).encode(), 21
        )

    def local_validate(
        self, raw,
        index=0,
        modify=None
    ):

        distribution = self.distribution(
            raw, index
        )

        entry = distribution.packages[index]

        if modify is not None:
            entry = modify(entry)

        path = self.folder / "test.zip"
        path.write_bytes(raw)

        device = self.ng if index == 0 else self.ne

        return package.validate_zip(
            path, entry, device
        )

    def rejected(self, raw, error, **kwargs):

        with self.assertRaisesRegex(
            package.PackageError,
            "^" + error + "$",
        ):
            self.local_validate(raw, **kwargs)

    def test_valid_ng_zip(self):

        result = self.local_validate(make_zip())

        self.assertEqual(result["members"], 2)

    def test_valid_ne_zip(self):

        result = self.local_validate(
            make_zip(bits=64, machine=183),
            index=1,
        )

        self.assertEqual(result["members"], 2)

    def test_wrong_sha256(self):

        self.rejected(
            make_zip(),
            "PACKAGE_SHA256_MISMATCH",
            modify=lambda p: replace(
                p, sha256="a" * 64
            ),
        )

    def test_wrong_size(self):

        self.rejected(
            make_zip(),
            "PACKAGE_SIZE_MISMATCH",
            modify=lambda p: replace(
                p, size=p.size + 1
            ),
        )

    def test_wrong_elf_class(self):

        self.rejected(
            make_zip(bits=64, machine=183),
            "ELF_CLASS_MISMATCH",
        )

    def test_wrong_elf_machine(self):

        self.rejected(
            make_zip(machine=62),
            "ELF_MACHINE_MISMATCH",
        )

    def test_wrong_addon_version(self):

        self.rejected(
            make_zip(addon_version="21.2.7"),
            "ZIP_VERSION_MISMATCH",
        )

    def test_wrong_addon_id(self):

        self.rejected(
            make_zip(addon_id="service.other"),
            "INVALID_ZIP_ADDON_XML",
        )

    def test_missing_binary(self):

        self.rejected(
            make_zip(include_binary=False),
            "MISSING_TVHEADEND_BINARY",
        )

    def test_unsafe_paths(self):

        for name in (
            "../outside",
            "/absolute",
            ROOT + "/../outside",
            ROOT + "/bin/../../outside",
            ROOT + "/bin\\other",
            ROOT + "/C:other",
            ROOT + "/bin//other",
            "service.other/file",
        ):

            with self.subTest(name=name):

                self.rejected(
                    make_zip(extras=[(name, b"x")]),
                    "UNSAFE_ZIP_PATH",
                )

    def test_duplicate_member(self):

        with warnings.catch_warnings():

            warnings.simplefilter("ignore", UserWarning)

            raw = make_zip(
                extras=[
                    (ROOT + "/addon.xml", b"duplicate")
                ]
            )

        self.rejected(
            raw, "DUPLICATE_ZIP_PATH"
        )

    def test_symlink_rejected(self):

        info = zipfile.ZipInfo(
            ROOT + "/bin/link"
        )

        info.create_system = 3

        info.external_attr = (
            (stat.S_IFLNK | 0o777) << 16
        )

        self.rejected(
            make_zip(extras=[(info, b"/storage")]),
            "UNSAFE_ZIP_FILE_TYPE",
        )

    def test_file_directory_conflict(self):

        self.rejected(
            make_zip(extras=[
                (ROOT + "/data", b"x"),
                (ROOT + "/data/file", b"y"),
            ]),
            "ZIP_PARENT_FILE_CONFLICT",
        )

    def test_invalid_zip(self):

        self.rejected(
            b"not a zip",
            "INVALID_PACKAGE_ZIP",
        )

    def test_manifest_not_published(self):

        def opener(request, timeout):

            raise package.urllib.error.HTTPError(
                request.full_url,
                404,
                "Not Found",
                {},
                None,
            )

        with self.assertRaises(
            package.ManifestNotPublished
        ):
            package.fetch_manifest(
                "21", BASE, opener
            )

    def test_manifest_permission_error_is_failure(self):

        def opener(request, timeout):

            raise package.urllib.error.HTTPError(
                request.full_url,
                403,
                "Forbidden",
                {},
                None,
            )

        with self.assertRaisesRegex(
            package.PackageError,
            "^HTTP_DOWNLOAD_FAILED$",
        ):
            package.fetch_manifest(
                "21", BASE, opener
            )

    def test_missing_zip_is_failure(self):

        raw = make_zip()

        distribution = self.distribution(raw)

        def opener(request, timeout):

            raise package.urllib.error.HTTPError(
                request.full_url,
                404,
                "Not Found",
                {},
                None,
            )

        with self.assertRaisesRegex(
            package.PackageError,
            "^HTTP_DOWNLOAD_FAILED$",
        ):
            with package.stage_update(
                distribution,
                self.ng,
                "21.2.7",
                "21",
                BASE,
                self.folder,
                opener,
            ):
                self.fail("MISSING_PACKAGE_ACCEPTED")

    def test_fetch_manifest(self):

        raw = json.dumps(self.data).encode()

        def opener(request, timeout):
            self.assertEqual(
                request.full_url,
                BASE + "/" + package.MANIFEST_PATH,
            )

            return FakeResponse(
                raw, request.full_url
            )

        result = package.fetch_manifest(
            "21", BASE, opener
        )

        self.assertEqual(result.kodi_major, 21)
        self.assertEqual(len(result.packages), 2)

    def test_invalid_cloud_route(self):

        for branch, base in (
            ("develop", BASE),
            ("21", BASE.replace("/21", "/develop")),
            ("21", "https://example.com/21"),
        ):

            with self.assertRaises(package.PackageError):

                package.fetch_manifest(
                    branch, base,
                    opener=self.forbidden,
                )

    def forbidden(self, *args, **kwargs):

        self.fail("Unexpected network request")

    def test_redirect_blocked(self):

        with self.assertRaisesRegex(
            package.PackageError,
            "^HTTP_REDIRECT_BLOCKED$",
        ):

            package.NoRedirect().redirect_request(
                None, None, 302, "", {},
                "https://example.com/file",
            )

    def test_response_url_mismatch(self):

        def opener(request, timeout):

            return FakeResponse(
                b"data",
                "https://example.com/file",
            )

        with self.assertRaisesRegex(
            package.PackageError,
            "^HTTP_URL_MISMATCH$",
        ):

            package.fetch_manifest(
                "21", BASE, opener
            )

    def test_stream_size_limit(self):

        def opener(request, timeout):

            return FakeResponse(
                b"x" * (
                    manifest.MAX_MANIFEST_BYTES + 1
                ),
                request.full_url,
                headers={},
            )

        with self.assertRaisesRegex(
            package.PackageError,
            "^DOWNLOAD_SIZE_LIMIT$",
        ):

            package.fetch_manifest(
                "21", BASE, opener
            )

    def test_staged_download_and_cleanup(self):

        raw = make_zip()

        distribution = self.distribution(raw)

        def opener(request, timeout):

            self.assertEqual(
                request.full_url,
                BASE + "/" +
                distribution.packages[0].path,
            )

            return FakeResponse(
                raw, request.full_url
            )

        with package.stage_update(
            distribution, self.ng,
            "21.2.7", "21", BASE,
            self.folder, opener,
        ) as (decision, path):

            self.assertEqual(
                decision.status,
                version.UPDATE_AVAILABLE,
            )

            self.assertEqual(
                path.read_bytes(), raw
            )

            staged = path

        self.assertFalse(staged.exists())
        self.assertEqual(
            list(self.folder.iterdir()), []
        )

    def test_failed_download_cleanup(self):

        raw = make_zip()

        distribution = self.distribution(raw)

        def opener(request, timeout):

            return FakeResponse(
                b"X" * len(raw),
                request.full_url,
            )

        with self.assertRaisesRegex(
            package.PackageError,
            "^PACKAGE_SHA256_MISMATCH$",
        ):

            with package.stage_update(
                distribution, self.ng,
                "21.2.7", "21", BASE,
                self.folder, opener,
            ):

                self.fail("Unverified package delivered")

        self.assertEqual(
            list(self.folder.iterdir()), []
        )

    def test_no_update_no_download(self):

        distribution = self.distribution(
            make_zip()
        )

        for installed in ("21.2.8", "21.2.9"):

            with package.stage_update(
                distribution, self.ng,
                installed, "21", BASE,
                self.folder, self.forbidden,
            ) as (decision, path):

                self.assertIsNone(path)

                self.assertNotEqual(
                    decision.status,
                    version.UPDATE_AVAILABLE,
                )

        self.assertEqual(
            list(self.folder.iterdir()), []
        )

    def test_unvalidated_build_no_download(self):

        distribution = self.distribution(
            make_zip(), authorized=False
        )

        with self.assertRaisesRegex(
            manifest.ManifestError,
            "^COREELEC_BUILD_NOT_VALIDATED$",
        ):

            with package.stage_update(
                distribution, self.ng,
                "21.2.7", "21", BASE,
                self.folder, self.forbidden,
            ):

                self.fail("Unauthorized package delivered")


if __name__ == "__main__":
    unittest.main()
