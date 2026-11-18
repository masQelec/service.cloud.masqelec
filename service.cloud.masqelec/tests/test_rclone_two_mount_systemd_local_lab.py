# -*- coding: utf-8 -*-
"""systemd REAL laboratory: synthetic tests must never invoke systemd."""
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / (
    "tools/rclone_two_mount_systemd_local_lab.py")
spec = importlib.util.spec_from_file_location("masqelec_sd_local_lab", PATH)
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

ROOT = Path("/tmp/masqelec-sd-lab-0123456789abcdef")
RCLONE = "/storage/.config/rclone/rclone"


def fixture_mountinfo(root=ROOT, *, duplicate=None, same_device=False,
                      wrong_folder=False, missing=None):
    roots, binds, _ = lab._layout(root)
    records = []
    for index, point in enumerate(roots):
        dev = "0:80" if same_device else "0:{}".format(80+index)
        records.append(
            "50 1 {} / {} rw - fuse.rclone account{}: rw".format(
                dev, point, index+1))
    for index, folder, target in binds:
        if target == missing:
            continue
        dev = "0:{}".format(80+index)
        fsroot = ("/wrong" if wrong_folder and folder == "movies"
                  and index == 0 else "/" + folder)
        records.append(
            "51 1 {} {} {} rw - fuse.rclone account{}: rw".format(
                dev, fsroot, target, index+1))
    if duplicate:
        for line in records:
            if (" " + duplicate + " ") in line:
                records.append(line)
                break
    return "\n".join(records)


class SystemdLocalLabTests(unittest.TestCase):
    def setUp(self):
        # Runner CI no necesita tener rclone instalado; simular su ruta.
        patcher = mock.patch.object(lab, "rclone_binary", return_value=RCLONE)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_lab_identity_permits_only_random_tmp(self):
        self.assertEqual(lab._identity(ROOT), ROOT.name)
        for bad in (
                "/storage/.mnt", "/tmp", "/tmp/masqelec-sd-lab-abc",
                "/tmp/masqelec-sd-lab-0123456789abcdef/extra",
                "/run/masqelec-sd-lab-0123456789abcdef"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                lab._identity(bad)

    def test_layout_never_includes_kodi_targets(self):
        fuse, binds, fixtures = lab._layout(ROOT)
        self.assertEqual(len(fuse), 2)
        self.assertEqual(len(binds), 4)
        self.assertEqual(len(fixtures), 2)
        all_dest = fuse + [x[2] for x in binds]
        self.assertEqual(len(set(all_dest)), 6)
        self.assertTrue(all(path.startswith(str(ROOT) + "/")
                            for path in all_dest))
        self.assertFalse(any(path.startswith("/storage")
                             for path in all_dest))

    def test_exactly_six_unique_random_systemd_names(self):
        names = lab._unit_names(ROOT)
        self.assertEqual(len(names["fuse"]), 2)
        self.assertEqual(len(names["bind"]), 4)
        self.assertEqual(len(set(names["fuse"]+names["bind"])), 6)
        self.assertTrue(all(name.startswith(ROOT.name + "-")
                            for name in names["fuse"]+names["bind"]))
        self.assertTrue(all(name.endswith(".service")
                            for name in names["fuse"]+names["bind"]))

    def test_units_use_type_simple_and_oneshot_with_binds_to(self):
        units = lab._unit_files(ROOT, RCLONE)
        names = lab._unit_names(ROOT)
        self.assertEqual(len(units), 6)
        for unit in names["fuse"]:
            text = units[unit].decode()
            self.assertIn("Type=simple", text)
            self.assertIn("--config /dev/null", text)
            self.assertIn("--read-only", text)
            self.assertIn("--vfs-cache-mode off", text)
            self.assertIn("Restart=no", text)
            self.assertNotIn("Type=notify", text)
        for unit in names["bind"]:
            text = units[unit].decode()
            self.assertIn("Type=oneshot", text)
            self.assertIn("BindsTo=", text)
            self.assertIn("After=", text)
            self.assertIn("/bin/mount --bind ", text)
            self.assertIn("ExecStop=/bin/umount ", text)
            self.assertIn("done; exit 1", text)
            self.assertNotIn("WantedBy=", text)
        for content in units.values():
            self.assertNotIn(b"/storage/.mnt", content)
            self.assertNotIn(b"rclone.conf", content)
            self.assertNotIn(b"users_library_", content)

    def test_unit_generation_rejects_unsafe_executable(self):
        for binary in ("rclone", "/tmp/rclone;touch-bad", "/tmp/r clone",
                       "/tmp/a\nExecStart=evil"):
            with self.subTest(binary=binary), self.assertRaises(ValueError):
                lab._unit_files(ROOT, binary)

    def test_mountinfo_six_entries_pass(self):
        self.assertTrue(lab._check_mounts(fixture_mountinfo(), ROOT))

    def test_stacked_mounts_rejected(self):
        fuse, binds, _ = lab._layout(ROOT)
        for dest in (fuse[0], fuse[1], binds[0][2], binds[3][2]):
            with self.subTest(dest=dest):
                self.assertFalse(lab._check_mounts(
                    fixture_mountinfo(duplicate=dest), ROOT))

    def test_same_superblock_root_rejected(self):
        self.assertFalse(lab._check_mounts(
            fixture_mountinfo(same_device=True), ROOT))

    def test_missing_bind_or_wrong_fsroot_rejected(self):
        binds = lab._layout(ROOT)[1]
        self.assertFalse(lab._check_mounts(
            fixture_mountinfo(missing=binds[1][2]), ROOT))
        self.assertFalse(lab._check_mounts(
            fixture_mountinfo(wrong_folder=True), ROOT))

    def test_truncated_mountinfo_rejected(self):
        self.assertFalse(lab._check_mounts("broken", ROOT))

    def test_no_credentials_inherited_in_subprocess(self):
        vars = {"PATH": "/usr/bin", "RCLONE_CONFIG": "/storage/secret",
                "AWS_SECRET_ACCESS_KEY": "key", "ONEDRIVE_TOKEN": "token",
                "GOOGLE_APPLICATION_CREDENTIALS": "hidden"}
        with mock.patch.dict(os.environ, vars, clear=True):
            self.assertEqual(lab._clean_env(), {"PATH": "/usr/bin"})

    def test_preflight_read_only_no_mutation(self):
        ready = {"root": True, "rclone": True, "fuse": True}
        with mock.patch.object(lab, "prerequisites", return_value=ready), \
             mock.patch.object(lab, "run_isolated",
                               side_effect=AssertionError("cannot execute")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--preflight"]), 0)
        self.assertIn("READY_FOR_ISOLATED_SYSTEMD", out.getvalue())
        self.assertIn("ONEDRIVE_ACCESSED=NO", out.getvalue())

    def test_preflight_blocks_prior_run_leftovers(self):
        def listing(path):
            if path == lab.TMP:
                return ["masqelec-sd-lab-0123456789abcdef"]
            return []
        with mock.patch.object(lab.os, "listdir", side_effect=listing):
            self.assertFalse(lab._no_prior_lab())

    def test_preflight_blocks_remaining_runtime_unit(self):
        def listing(path):
            if path == lab.RUNTIME_UNITS:
                return ["masqelec-sd-lab-0123456789abcdef-fuse1.service"]
            return []
        with mock.patch.object(lab.os, "listdir", side_effect=listing):
            self.assertFalse(lab._no_prior_lab())

    def test_preflight_allows_unrelated_legacy_units(self):
        def listing(path):
            if path == lab.RUNTIME_UNITS:
                return ["rclone_videos_1.service", "rclone_tvshows_2.service"]
            return ["masqelec-fuse-local-old", "something-else"]
        with mock.patch.object(lab.os, "listdir", side_effect=listing):
            self.assertTrue(lab._no_prior_lab())

    def test_unreadable_mount_unit_dir_blocks_another_run(self):
        with mock.patch.object(lab.os, "listdir",
                               side_effect=OSError("permission denied")):
            self.assertFalse(lab._no_prior_lab())

    def test_temp_allocation_failure_returns_closed_status(self):
        with mock.patch.object(lab, "prerequisites",
                               return_value={"ok": True}), \
             mock.patch.object(lab, "_create_root",
                               side_effect=OSError("readonly")):
            self.assertEqual(
                lab.run_isolated(),
                "FAIL_CANNOT_ALLOCATE_ISOLATED_TMP")

    def test_preflight_missing_systemd_blocks(self):
        with mock.patch.object(
                lab, "prerequisites",
                return_value={"systemd_online": False}), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--preflight"]), 2)
        self.assertIn("SYSTEMD_ONLINE=NO", out.getvalue())

    def test_pilot_without_explicit_confirmation_blocks(self):
        with mock.patch.object(lab, "run_isolated",
                               side_effect=AssertionError("must not run")), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(["--run-isolated-systemd"]), 2)
        self.assertIn("BLOCKED_INVALID_MODE", out.getvalue())

    def test_full_success_with_synthetic_systemctl(self):
        names = lab._unit_names(ROOT)
        calls = []
        def control(op, unit=None, **kw):
            calls.append((op, unit))
            return True
        with mock.patch.object(lab, "prerequisites",
                               return_value={"ok": True}), \
             mock.patch.object(lab, "_create_root", return_value=ROOT), \
             mock.patch.object(lab, "_prepare_dirs"), \
             mock.patch.object(lab, "_any_lab_mounted", return_value=False), \
             mock.patch.object(lab, "_write_units"), \
             mock.patch.object(lab, "_control", side_effect=control), \
             mock.patch.object(lab, "_is_active", return_value=True), \
             mock.patch.object(lab, "_read_mountinfo",
                               return_value=fixture_mountinfo()), \
             mock.patch.object(lab, "_read_sample", return_value=True), \
             mock.patch.object(lab, "_cleanup", return_value=True), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            value = lab.run_isolated()
        self.assertEqual(value, "PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL")
        starts = [unit for op, unit in calls if op == "start"]
        self.assertEqual(starts, names["fuse"] + names["bind"])
        self.assertIn("CLEANUP=COMPLETE", out.getvalue())

    def test_diagnostic_classifies_bind_failure_from_systemd(self):
        unit = lab._unit_names(ROOT)["bind"][0]
        raw = (b"LoadState=loaded\nActiveState=failed\n"
               b"SubState=failed\nResult=exit-code\n"
               b"ExecMainStatus=0\n"
               b"ExecStartPre={ path=/bin/sh ; code=exited ; status=1 }\n")
        with mock.patch.object(lab, "_run",
                               return_value=(True, raw)):
            data = lab._service_diagnostic(unit, ROOT)
        self.assertEqual(data["FAILED_STAGE"], "BIND_VIDEOS_1")
        self.assertEqual(data["SYSTEMD_PRE_STATUS"], "1")
        self.assertEqual(data["SYSTEMD_DIAG_CLASS"], "EXECSTARTPRE_FAILURE")

    def test_diagnostic_classifies_missing_binary_in_fuse(self):
        unit = lab._unit_names(ROOT)["fuse"][1]
        raw = (b"LoadState=loaded\nActiveState=failed\n"
               b"Result=exit-code\nExecMainStatus=203\n")
        with mock.patch.object(lab, "_run",
                               return_value=(True, raw)):
            data = lab._service_diagnostic(unit, ROOT)
        self.assertEqual(data["FAILED_STAGE"], "FUSE_2")
        self.assertEqual(data["SYSTEMD_DIAG_CLASS"], "EXEC_NOT_FOUND")

    def test_diagnostic_systemctl_unsupported_fails_closed(self):
        unit = lab._unit_names(ROOT)["bind"][3]
        with mock.patch.object(lab, "_run", return_value=(False, b"")):
            data = lab._service_diagnostic(unit, ROOT)
        self.assertEqual(data["FAILED_STAGE"], "BIND_TVSHOWS_2")
        self.assertEqual(data["SYSTEMD_RESULT"], "UNKNOWN")
        self.assertEqual(data["SYSTEMD_DIAG_CLASS"], "UNCLASSIFIED")

    def test_diagnostic_ignores_untrusted_property_values_and_tokens(self):
        unit = lab._unit_names(ROOT)["fuse"][0]
        bad = (b"LoadState=loaded; TOKEN=hidden\n"
               b"Result=exit-code\nExecMainStatus=1\n"
               b"ExecStart=/private/secret-token\n")
        with mock.patch.object(lab, "_run", return_value=(True, bad)), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            lab._emit_service_diagnostic(unit, ROOT)
        self.assertNotIn("secret-token", output.getvalue())
        self.assertNotIn("TOKEN=hidden", output.getvalue())
        self.assertIn("FAILED_STAGE=FUSE_1", output.getvalue())

    def test_diagnostic_invalid_unit_never_queries_systemd(self):
        with mock.patch.object(lab, "_run",
                               side_effect=AssertionError("no call")):
            diag = lab._service_diagnostic("rclone_videos_1.service", ROOT)
        self.assertEqual(diag["FAILED_STAGE"], "INVALID_LAB_UNIT")

    def test_service_start_failure_cleans_and_never_passes(self):
        def control(op, unit=None, **kw):
            return not (op == "start" and
                        unit == lab._unit_names(ROOT)["bind"][1])
        with mock.patch.object(lab, "prerequisites",
                               return_value={"ok": True}), \
             mock.patch.object(lab, "_create_root", return_value=ROOT), \
             mock.patch.object(lab, "_prepare_dirs"), \
             mock.patch.object(lab, "_any_lab_mounted", return_value=False), \
             mock.patch.object(lab, "_write_units"), \
             mock.patch.object(lab, "_control", side_effect=control), \
             mock.patch.object(lab, "_emit_service_diagnostic") as diagnostic, \
             mock.patch.object(lab, "_cleanup", return_value=True):
            self.assertEqual(lab.run_isolated(), "FAIL_SERVICE_START")
        diagnostic.assert_called_once_with(
            lab._unit_names(ROOT)["bind"][1], ROOT)

    def test_cleanup_failure_overrides_success_without_false_pass(self):
        with mock.patch.object(lab, "prerequisites",
                               return_value={"ok": True}), \
             mock.patch.object(lab, "_create_root", return_value=ROOT), \
             mock.patch.object(lab, "_prepare_dirs"), \
             mock.patch.object(lab, "_any_lab_mounted", return_value=False), \
             mock.patch.object(lab, "_write_units"), \
             mock.patch.object(lab, "_control", return_value=True), \
             mock.patch.object(lab, "_is_active", return_value=True), \
             mock.patch.object(lab, "_read_mountinfo",
                               return_value=fixture_mountinfo()), \
             mock.patch.object(lab, "_read_sample", return_value=True), \
             mock.patch.object(lab, "_cleanup", return_value=False), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            result = lab.run_isolated()
        self.assertEqual(result, "FAIL_SYSTEMD_CLEANUP")
        self.assertIn("CLEANUP=INCOMPLETE_REVIEW_MANUALLY", out.getvalue())
        self.assertIn("LAB_TEMP_ROOT=", out.getvalue())

    def test_stale_lab_mount_cannot_start_services(self):
        with mock.patch.object(lab, "prerequisites",
                               return_value={"ok": True}), \
             mock.patch.object(lab, "_create_root", return_value=ROOT), \
             mock.patch.object(lab, "_prepare_dirs"), \
             mock.patch.object(lab, "_any_lab_mounted", return_value=True), \
             mock.patch.object(lab, "_write_units",
                               side_effect=AssertionError("no writes")), \
             mock.patch.object(lab, "_cleanup", return_value=True):
            self.assertEqual(lab.run_isolated(),
                             "BLOCKED_UNEXPECTED_LAB_MOUNT")

    def test_cleanup_stops_binds_before_fuse(self):
        names = lab._unit_names(ROOT)
        calls = []
        def control(op, unit=None, **kw):
            calls.append((op, unit))
            return True
        with mock.patch.object(lab, "_control", side_effect=control), \
             mock.patch.object(lab, "_read_mountinfo", return_value=""), \
             mock.patch.object(lab, "_any_lab_mounted", return_value=False), \
             mock.patch.object(lab, "_is_active", return_value=False), \
             mock.patch.object(lab, "_remove_exact_units",
                               return_value=True), \
             mock.patch.object(lab.shutil, "rmtree"):
            self.assertTrue(lab._cleanup(
                ROOT, lab._unit_files(ROOT, RCLONE)))
        stops = [unit for op, unit in calls if op == "stop"]
        self.assertEqual(stops, list(reversed(names["bind"])) +
                         list(reversed(names["fuse"])))
        self.assertTrue(all(name.startswith(ROOT.name) for name in stops))

    def test_cleanup_busy_mounts_preserved_for_manual_review(self):
        names = lab._unit_names(ROOT)
        with mock.patch.object(lab, "_control", return_value=True), \
             mock.patch.object(lab, "_read_mountinfo",
                               return_value=fixture_mountinfo()), \
             mock.patch.object(lab, "_any_lab_mounted", return_value=True), \
             mock.patch.object(lab, "_is_active", return_value=False), \
             mock.patch.object(lab, "_run", return_value=(False, b"")), \
             mock.patch.object(lab.shutil, "rmtree",
                               side_effect=AssertionError("unsafe deletion")):
            self.assertFalse(lab._cleanup(
                ROOT, lab._unit_files(ROOT, RCLONE)))

    def test_unit_install_no_clobber_and_safe_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            units = lab._unit_files(ROOT, RCLONE)
            with mock.patch.object(lab, "RUNTIME_UNITS", temp):
                names = lab._write_units(units)
                self.assertEqual(len(names), 6)
                with self.assertRaises(FileExistsError):
                    lab._write_units(units)
                self.assertTrue(lab._remove_exact_units(units))
                self.assertEqual(list(Path(temp).iterdir()), [])

    def test_unit_modification_blocks_removal(self):
        with tempfile.TemporaryDirectory() as temp:
            units = lab._unit_files(ROOT, RCLONE)
            with mock.patch.object(lab, "RUNTIME_UNITS", temp):
                lab._write_units(units)
                target = Path(temp, next(iter(units)))
                target.write_bytes(b"unexpected bytes")
                self.assertFalse(lab._remove_exact_units(units))
                self.assertTrue(target.exists())

    def test_cli_pass_requires_real_isolated_result(self):
        with mock.patch.object(lab, "run_isolated",
                               return_value="PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL"), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(lab.main(
                ["--run-isolated-systemd", "--confirm-isolated-only"]), 0)
        self.assertIn("PERMANENT_UNITS_ENABLED=NO", out.getvalue())
        self.assertIn("LEGACY_SERVICE_START_STOP=NO", out.getvalue())

    def test_source_has_no_production_mounts_or_oauth(self):
        source = PATH.read_text(encoding="utf-8")
        self.assertNotIn('"/storage/.config/rclone/rclone.conf"', source)
        self.assertNotIn("rclone lsf", source)
        self.assertNotIn("systemctl enable", source)
        self.assertNotIn('["systemctl", "disable"', source)
        self.assertNotIn("oauth_tokens", source)


if __name__ == "__main__":
    unittest.main()
