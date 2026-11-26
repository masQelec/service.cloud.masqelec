# -*- coding: utf-8 -*-
"""Identificacion NG/NE sin CoreELEC ni Kodi reales."""

import tempfile
import unittest

from pathlib import Path
from lib import tvheadend_platform as platform


MASTER = """
NAME="CoreELEC"
VERSION="21.2.5-Omega_devel_20250919152246"
ID="coreelec"
VERSION_ID="21.2.5"
LIBREELEC_ARCH="Amlogic-ng.arm"
COREELEC_ARCH="Amlogic-ng.arm"
COREELEC_DEVICE="Amlogic-ng"
"""

NE = """
ID=coreelec
VERSION_ID=21.2.5
COREELEC_ARCH=Amlogic-ne.aarch64
LIBREELEC_ARCH=Amlogic-ne.aarch64
COREELEC_DEVICE=Amlogic-ne
"""


class TvheadendPlatformTests(unittest.TestCase):

    def test_master_ng_observed(self):
        result = platform.detect_from_text(MASTER)

        self.assertEqual(result.target, "Amlogic-ng.arm")
        self.assertEqual(result.device, "Amlogic-ng")
        self.assertEqual(result.architecture, "arm")
        self.assertEqual(result.elf_bits, 32)
        self.assertEqual(result.elf_machine, 40)
        self.assertEqual(result.coreelec_version, "21.2.5")
        self.assertEqual(
            result.coreelec_build,
            "21.2.5-Omega_devel_20250919152246"
        )

    def test_ne_simulated(self):
        result = platform.detect_from_text(NE)

        self.assertEqual(result.target, "Amlogic-ne.aarch64")
        self.assertEqual(result.device, "Amlogic-ne")
        self.assertEqual(result.architecture, "aarch64")
        self.assertEqual(result.elf_bits, 64)
        self.assertEqual(result.elf_machine, 183)

    def test_unknown_architecture(self):
        for target in (
            "Amlogic-ne.arm",
            "Amlogic-ng.aarch64",
            "Amlogic-ce.arm",
            "Generic.x86_64",
            "aarch64",
        ):
            with self.subTest(target=target):
                with self.assertRaisesRegex(
                    platform.PlatformError,
                    "^UNSUPPORTED_COREELEC_ARCH$"
                ):
                    platform.detect_from_text(
                        MASTER.replace(
                            "Amlogic-ng.arm", target
                        )
                    )

    def test_kernel_arch_is_not_distribution_arch(self):
        result = platform.detect_from_text(
            MASTER + "\nKERNEL_ARCH=aarch64\n"
        )

        self.assertEqual(result.architecture, "arm")
        self.assertEqual(result.elf_bits, 32)

    def test_conflicting_device(self):
        with self.assertRaisesRegex(
            platform.PlatformError,
            "^COREELEC_DEVICE_MISMATCH$"
        ):
            platform.detect_from_text(
                MASTER.replace(
                    'COREELEC_DEVICE="Amlogic-ng"',
                    'COREELEC_DEVICE="Amlogic-ne"'
                )
            )

    def test_conflicting_architecture(self):
        with self.assertRaisesRegex(
            platform.PlatformError,
            "^COREELEC_ARCH_MISMATCH$"
        ):
            platform.detect_from_text(
                MASTER.replace(
                    'LIBREELEC_ARCH="Amlogic-ng.arm"',
                    'LIBREELEC_ARCH="Amlogic-ne.aarch64"'
                )
            )

    def test_unsupported_os(self):
        with self.assertRaisesRegex(
            platform.PlatformError,
            "^UNSUPPORTED_OS$"
        ):
            platform.detect_from_text(
                MASTER.replace(
                    'ID="coreelec"',
                    'ID="libreelec"'
                )
            )

    def test_invalid_version(self):
        for version in ("unknown", "21", "21.2.beta", "021.2"):
            with self.subTest(version=version):
                with self.assertRaisesRegex(
                    platform.PlatformError,
                    "^INVALID_COREELEC_VERSION$"
                ):
                    platform.detect_from_text(
                        MASTER.replace(
                            'VERSION_ID="21.2.5"',
                            f'VERSION_ID="{version}"'
                        )
                    )

    def test_duplicate_key_rejected(self):
        with self.assertRaisesRegex(
            platform.PlatformError,
            "^DUPLICATE_OS_RELEASE_KEY$"
        ):
            platform.detect_from_text(
                MASTER + "\nCOREELEC_ARCH=Amlogic-ne.aarch64\n"
            )

    def test_missing_primary_architecture_no_fallback(self):
        with self.assertRaisesRegex(
            platform.PlatformError,
            "^UNSUPPORTED_COREELEC_ARCH$"
        ):
            platform.detect_from_text(
                MASTER.replace(
                    'COREELEC_ARCH="Amlogic-ng.arm"', ""
                )
            )

    def test_shell_syntax_rejected(self):
        with self.assertRaisesRegex(
            platform.PlatformError,
            "^INVALID_OS_RELEASE_VALUE$"
        ):
            platform.detect_from_text(
                MASTER.replace(
                    'COREELEC_ARCH="Amlogic-ng.arm"',
                    'COREELEC_ARCH="$(uname -m)"'
                )
            )

    def test_read_local_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_text(MASTER, encoding="utf-8")

            result = platform.detect(path)

            self.assertEqual(
                result.target, "Amlogic-ng.arm"
            )

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                platform.PlatformError,
                "^OS_RELEASE_UNAVAILABLE$"
            ):
                platform.detect(
                    Path(tmp) / "missing"
                )

    def test_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"

            path.write_bytes(
                b"A" * (platform.MAX_OS_RELEASE_BYTES + 1)
            )

            with self.assertRaisesRegex(
                platform.PlatformError,
                "^OS_RELEASE_TOO_LARGE$"
            ):
                platform.detect(path)

    def test_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "os-release"
            path.write_bytes(b"\xff\xfe")

            with self.assertRaisesRegex(
                platform.PlatformError,
                "^OS_RELEASE_UNAVAILABLE$"
            ):
                platform.detect(path)


if __name__ == "__main__":
    unittest.main()
