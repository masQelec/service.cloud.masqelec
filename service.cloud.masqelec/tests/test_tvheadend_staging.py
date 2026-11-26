# -*- coding: utf-8 -*-

import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
import zipfile

from pathlib import Path
from unittest import mock

from lib import tvheadend_staging as staging
from lib import tvheadend_manifest as manifest
from lib import tvheadend_platform as platform
from lib import tvheadend_package as package

from test_tvheadend_platform import MASTER
from test_tvheadend_manifest import CANDIDATE
from test_tvheadend_package import make_zip


def executable_zip(executable=True):

    original = make_zip(
        extras=[
            (
                manifest.ADDON_ID + "/bin/tv_grab_file",
                b"factory-grabber",
            ),
        ],
    )

    output = io.BytesIO()

    with zipfile.ZipFile(io.BytesIO(original)) as source:

        with zipfile.ZipFile(
            output, "w", zipfile.ZIP_DEFLATED
        ) as target:

            for info in source.infolist():

                mode = 0o644

                if (
                    info.filename.endswith("/bin/tvheadend")
                    and executable
                ):
                    mode = 0o755

                info.create_system = 3

                info.external_attr = (
                    (stat.S_IFREG | mode) << 16
                )

                target.writestr(
                    info,
                    source.read(info.filename),
                )

    return output.getvalue()


class TvheadendStagingTests(unittest.TestCase):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(self.tmp.name).resolve()

        self.root = self.base / "transaction"
        self.root.mkdir(mode=0o700)

        self.grabber = self.base / "tv_grab_file"

        self.custom = b"#!/bin/sh\n# masQelec\n"

        self.grabber.write_bytes(self.custom)

        self.device = platform.detect_from_text(
            MASTER
        )

        self.candidate = self.root / "candidate"

        self.load_zip(executable_zip())

    def load_zip(self, raw):

        self.zip = self.base / "package.zip"
        self.zip.write_bytes(raw)

        data = json.loads(
            CANDIDATE.read_text(encoding="utf-8")
        )

        data["packages"][0]["size"] = len(raw)

        data["packages"][0]["sha256"] = (
            hashlib.sha256(raw).hexdigest()
        )

        distribution = manifest.parse_manifest(
            json.dumps(data).encode(),
            21,
        )

        self.entry = distribution.packages[0]

    def prepare(self):

        return staging.prepare_candidate(
            self.zip,
            self.entry,
            self.device,
            self.root,
            self.grabber,
        )

    def test_prepare_candidate(self):

        result = self.prepare()

        self.assertEqual(
            result["candidate"],
            self.candidate,
        )

        self.assertEqual(
            result["version"], "21.2.8"
        )

    def test_custom_grabber_preserved(self):

        result = self.prepare()

        path = (
            self.candidate / "bin/tv_grab_file"
        )

        self.assertEqual(
            path.read_bytes(),
            self.custom,
        )

        self.assertEqual(
            result["grabber_sha256"],
            hashlib.sha256(
                self.custom
            ).hexdigest(),
        )

        self.assertEqual(
            self.grabber.read_bytes(),
            self.custom,
        )

    def test_executable_permissions(self):

        self.prepare()

        for name in (
            "bin/tvheadend",
            "bin/tv_grab_file",
        ):

            self.assertEqual(
                stat.S_IMODE(
                    (self.candidate / name)
                    .stat().st_mode
                ),
                0o755,
            )

    def test_existing_candidate_preserved(self):

        self.candidate.mkdir()

        marker = self.candidate / "marker"
        marker.write_text("existing backup")

        with self.assertRaisesRegex(
            staging.StagingError,
            "^CANDIDATE_ALREADY_EXISTS$",
        ):
            self.prepare()

        self.assertEqual(
            marker.read_text(),
            "existing backup",
        )

    def test_existing_journal_blocks(self):

        journal = self.root / "journal.json"
        journal.write_text("pending transaction")

        with self.assertRaisesRegex(
            staging.StagingError,
            "^TRANSACTION_ALREADY_EXISTS$",
        ):
            self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )

    def test_non_private_root_rejected(self):

        self.root.chmod(0o755)

        with self.assertRaisesRegex(
            staging.StagingError,
            "^STAGING_ROOT_NOT_PRIVATE$",
        ):
            self.prepare()

    def test_insufficient_space(self):

        with mock.patch.object(
            staging.shutil,
            "disk_usage",
            return_value=mock.Mock(free=0),
        ):

            with self.assertRaisesRegex(
                staging.StagingError,
                "^INSUFFICIENT_STAGING_SPACE$",
            ):
                self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )

    def test_empty_grabber_rejected(self):

        self.grabber.write_bytes(b"")

        with self.assertRaisesRegex(
            staging.StagingError,
            "^INVALID_GRABBER_SIZE$",
        ):
            self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )

    def test_symlink_grabber_rejected(self):

        self.grabber.unlink()

        self.grabber.symlink_to(self.zip)

        with self.assertRaises(OSError):
            self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )

    def test_corrupted_package_rejected(self):

        raw = self.zip.read_bytes()

        self.zip.write_bytes(
            b"X" * len(raw)
        )

        with self.assertRaises(
            package.PackageError
        ):
            self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )

    def test_extraction_failure_cleanup(self):

        with mock.patch.object(
            staging,
            "extract_validated_zip",
            side_effect=OSError("simulated error"),
        ):

            with self.assertRaises(OSError):
                self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )

    def test_non_executable_binary_rejected(self):

        self.load_zip(
            executable_zip(executable=False)
        )

        with self.assertRaisesRegex(
            staging.transaction.TransactionError,
            "^INVALID_EXECUTABLE$",
        ):
            self.prepare()

        self.assertFalse(
            self.candidate.exists()
        )


if __name__ == "__main__":
    unittest.main()
