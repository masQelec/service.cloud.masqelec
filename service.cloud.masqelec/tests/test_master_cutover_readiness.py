# -*- coding: utf-8 -*-
"""No credentials, mounts or services: synthetic readiness checks."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

script = Path(__file__).resolve().parents[1] / "tools/master_cutover_readiness.py"
spec = importlib.util.spec_from_file_location("master_readiness", script)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class MasterReadinessTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.system = self.root / "system.d"
        self.system.mkdir(mode=0o700)
        self.system.chmod(0o700)
        self.conf = self.root / "rclone.conf"
        self.conf.write_bytes(b"fixture-no-tokens")
        self.conf.chmod(0o600)
        self.parent = self.root / "masqelec"
        self.parent.mkdir(mode=0o700)
        self.parent.chmod(0o700)
        for name in gate.LEGACY:
            (self.system / name).write_text("fixture")
        patchers = [
            mock.patch.object(gate, "UNIT_DIR", str(self.system)),
            mock.patch.object(gate, "CANONICAL", str(self.conf)),
            mock.patch.object(gate, "PARENT", str(self.parent)),
            mock.patch.object(gate, "SPACE_ANCHOR", str(self.root)),
            mock.patch.object(gate, "TXN_PARENT", str(self.parent / "transaction")),
            mock.patch.object(gate, "ISOLATED_PARENT", str(self.parent / "isolated")),
            mock.patch.object(gate, "STATE", str(self.parent / "state.json")),
            mock.patch.object(gate, "_is_root", return_value=True),
        ]
        for p in patchers:
            p.start()
            self.addCleanup(p.stop)

    def test_fixture_readiness(self):
        self.assertTrue(all(gate.assess().values()))

    def test_missing_journal_base_is_safe_for_first_install(self):
        self.parent.rmdir()
        result = gate.assess()
        self.assertTrue(result["JOURNAL_PARENT_SAFE"])
        self.assertTrue(result["FREE_SPACE"])
        self.assertTrue(all(result.values()))
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(gate.main(["--read-only"]), 0)
        self.assertIn("JOURNAL_PARENT=ABSENT_BOOTSTRAP_REQUIRED",
                      out.getvalue())
        self.assertFalse(self.parent.exists())

    def test_symlink_journal_base_is_unsafe(self):
        self.parent.rmdir()
        self.parent.symlink_to(self.root)
        self.assertFalse(gate.assess()["JOURNAL_PARENT_SAFE"])

    def test_group_writable_storage_parent_blocks_bootstrap(self):
        self.parent.rmdir()
        self.root.chmod(0o777)
        self.assertFalse(gate.assess()["JOURNAL_PARENT_SAFE"])

    def test_non_root_blocks_cutover_readiness(self):
        with mock.patch.object(gate, "_is_root", return_value=False):
            self.assertFalse(gate.assess()["ROOT"])

    def test_group_writable_systemd_denied(self):
        self.system.chmod(0o775)
        self.assertFalse(gate.assess()["UNIT_DIRECTORY_SAFE"])

    def test_public_canonical_denied(self):
        self.conf.chmod(0o644)
        self.assertFalse(gate.assess()["CANONICAL_PRIVATE"])

    def test_existing_transaction_denied(self):
        (self.parent / "transaction").mkdir()
        self.assertFalse(gate.assess()["NO_TRANSACTION"])

    def test_new_service_denied(self):
        (self.system / gate.NEW[0]).write_text("fixture")
        self.assertFalse(gate.assess()["NEW_FILES_ABSENT"])

    def test_legacy_dropin_denied(self):
        (self.system / (gate.LEGACY[0] + ".d")).mkdir()
        self.assertFalse(gate.assess()["NO_LEGACY_DROPINS"])

    def test_read_only_cli_does_not_print_paths(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = gate.main(["--read-only"])
        self.assertEqual(result, 0)
        text = output.getvalue()
        self.assertIn("MASTER_READINESS=PASS_READ_ONLY", text)
        self.assertIn("CUTOVER_AUTHORIZED=NO", text)
        self.assertNotIn(str(self.root), text)
        self.assertNotIn("fixture-no-tokens", text)

    def test_invalid_mode_does_not_inspect(self):
        with mock.patch.object(gate, "assess",
                               side_effect=AssertionError("must not inspect")):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(gate.main(["--apply"]), 2)
        self.assertIn("BLOCKED_INVALID_MODE", out.getvalue())


if __name__ == "__main__":
    unittest.main()
