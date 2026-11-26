# -*- coding: utf-8 -*-

import tempfile
import unittest

from pathlib import Path
from unittest import mock

from lib import tvheadend_boot as boot
from lib import tvheadend_boot_install as install


class FakeSystemd:

    def __init__(self):

        self.calls = []
        self.ready = False
        self.valid_dependencies = True
        self.start_works = True

    def __call__(self, *args):

        self.calls.append(args)

        if args == ("daemon-reload",):
            return ""

        if args == ("start", boot.UNIT_NAME):

            if self.start_works:
                self.ready = True

            return ""

        if args[0] != "show":
            raise AssertionError(args)

        unit = args[-1]

        name = boot.UNIT_NAME

        if unit == boot.KODI_UNIT:

            values = {
                "LoadState": "loaded",
                "Wants": name,
                "Requires": "sysinit.target",
                "After": name,
            }

        elif unit == boot.TVH_UNIT:

            values = {
                "LoadState": "loaded",
                "Requires": (
                    name
                    if self.valid_dependencies
                    else ""
                ),
                "After": name,
            }

        elif unit == name:

            values = {
                "LoadState": "loaded",
                "Before": (
                    boot.KODI_UNIT
                    + " "
                    + boot.TVH_UNIT
                ),
                "Type": "oneshot",
                "RemainAfterExit": "yes",
                "ActiveState": (
                    "active"
                    if self.ready
                    else "inactive"
                ),
                "SubState": (
                    "exited"
                    if self.ready
                    else "dead"
                ),
                "Result": "success",
            }

        else:
            raise AssertionError(unit)

        names = [
            arg[2:]
            for arg in args
            if arg.startswith("-p")
        ]

        return "\n".join(
            f"{key}={values[key]}"
            for key in names
        )


class TvheadendBootInstallTests(
    unittest.TestCase
):

    def setUp(self):

        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

        self.base = Path(
            self.tmp.name
        ).resolve()

        self.folder = self.base / "system.d"
        self.folder.mkdir(mode=0o700)

        self.runner = self.base / "runner.py"
        self.runner.write_text("print('test')")

        self.root = self.base / "transaction"

        self.systemd = FakeSystemd()

        self.unit = (
            self.folder / boot.UNIT_NAME
        )

        self.kodi = (
            self.folder
            / "kodi.service.d"
            / boot.DROPIN_NAME
        )

        self.tvh = (
            self.folder
            / "service.tvheadend43.service.d"
            / boot.DROPIN_NAME
        )

    def ensure(self, authorized=True):

        return install.ensure_installed(
            authorized=authorized,
            folder=self.folder,
            runner=self.runner,
            transaction_root=self.root,
            ctl=self.systemd,
        )

    def allowed(self):

        with mock.patch.object(
            install,
            "is_coreelec_root",
            return_value=True,
        ):

            return self.ensure()

    def test_install_complete(self):

        self.assertEqual(
            self.allowed(), "READY"
        )

        self.assertEqual(
            self.unit.read_text(),
            boot.UNIT,
        )

        self.assertEqual(
            self.kodi.read_text(),
            boot.KODI_DROPIN,
        )

        self.assertEqual(
            self.tvh.read_text(),
            boot.TVH_DROPIN,
        )

        self.assertTrue(self.systemd.ready)

    def test_idempotent_install(self):

        self.allowed()

        inode = self.unit.stat().st_ino

        self.allowed()

        self.assertEqual(
            self.unit.stat().st_ino,
            inode,
        )

        starts = [
            call
            for call in self.systemd.calls
            if call[0] == "start"
        ]

        self.assertEqual(
            len(starts), 1
        )

    def test_unauthorized_install(self):

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^BOOT_INSTALL_NOT_AUTHORIZED$",
        ):

            self.ensure(False)

        self.assertEqual(
            list(self.folder.iterdir()), []
        )

    def test_platform_rejected(self):

        with mock.patch.object(
            install,
            "is_coreelec_root",
            return_value=False,
        ):

            with self.assertRaisesRegex(
                install.BootInstallError,
                "^BOOT_INSTALL_PLATFORM_REJECTED$",
            ):

                self.ensure()

        self.assertEqual(
            list(self.folder.iterdir()), []
        )

    def test_missing_runner(self):

        self.runner.unlink()

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^BOOT_RUNNER_MISSING$",
        ):

            self.allowed()

        self.assertFalse(
            self.unit.exists()
        )

    def test_existing_conflict_preserved(self):

        self.tvh.parent.mkdir(mode=0o700)

        self.tvh.write_text(
            "operator configuration"
        )

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^BOOT_INSTALL_CONFLICT$",
        ):

            self.allowed()

        self.assertEqual(
            self.tvh.read_text(),
            "operator configuration",
        )

        self.assertFalse(
            self.unit.exists()
        )

    def test_symlink_unit_rejected(self):

        self.unit.symlink_to(self.runner)

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^BOOT_INSTALL_CONFLICT$",
        ):

            self.allowed()

        self.assertTrue(
            self.unit.is_symlink()
        )

    def test_symlink_dropin_directory(self):

        self.kodi.parent.symlink_to(
            self.base
        )

        with self.assertRaises(ValueError):

            self.allowed()

        self.assertFalse(
            self.unit.exists()
        )

    def test_unconfirmed_dependencies(self):

        self.systemd.valid_dependencies = False

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^TVH_BOOT_DEPENDENCY_MISMATCH$",
        ):

            self.allowed()

        self.assertFalse(
            self.systemd.ready
        )

    def test_recovery_start_failure(self):

        self.systemd.start_works = False

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^RECOVERY_UNIT_NOT_READY$",
        ):

            self.allowed()

    def test_pending_transaction_blocks_install(self):

        self.root.mkdir()

        (
            self.root / "update.json"
        ).write_text("pending")

        with self.assertRaisesRegex(
            install.BootInstallError,
            "^BOOT_INSTALL_PENDING_TRANSACTION$",
        ):

            self.allowed()

        self.assertFalse(
            self.unit.exists()
        )

    def test_no_service_restart(self):

        self.allowed()

        disruptive = [
            call
            for call in self.systemd.calls
            if call[0] in (
                "restart",
                "stop",
                "disable",
                "enable",
            )
        ]

        self.assertEqual(disruptive, [])

        self.assertIn(
            ("start", boot.UNIT_NAME),
            self.systemd.calls,
        )


if __name__ == "__main__":
    unittest.main()
