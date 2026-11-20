# -*- coding: utf-8 -*-
"""Contrato: los checks periódicos del servicio NO recorren OneDrive."""
import ast
from pathlib import Path
import unittest


SERVICE = Path(__file__).resolve().parents[1] / "service.py"


def fn(name):
    tree = ast.parse(SERVICE.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) \
                and node.name == name:
            return node
    raise AssertionError("Expected service function absent: " + name)


def calls_inside(name):
    return [
        ast.unparse(call.func)
        for call in ast.walk(fn(name))
        if isinstance(call, ast.Call)
    ]


class RemoteScanFenceTests(unittest.TestCase):
    def test_v2_mount_health_does_not_use_remote_filesystem(self):
        calls = calls_inside("_two_mounts_ready")
        for forbidden in ("_safe_listdir", "os.listdir", "os.scandir",
                          "os.walk", "os.path.isdir", "os.stat",
                          "os.path.exists", "subprocess.run"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, calls)

    def test_legacy_mount_health_does_not_enumerate_onedrive(self):
        calls = calls_inside("_mounts_ready")
        for forbidden in ("_safe_listdir", "os.listdir", "os.scandir",
                          "os.walk", "os.stat", "os.path.isdir"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, calls)

    def test_both_paths_use_kernel_mount_tables(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn('with open("/proc/self/mountinfo"', source)
        self.assertIn('with open("/proc/mounts"', source)
        self.assertIn("check_two_fuse_four_bind(entries)", source)
        self.assertIn("required_targets - mounted_targets", source)

    def test_master_client_logic_not_replaced(self):
        source = SERVICE.read_text(encoding="utf-8")
        self.assertIn("core_catalog", source)
        self.assertIn("update_library", source)
        self.assertIn("REQUIRED_RCLONE_MOUNTS", source)


if __name__ == "__main__":
    unittest.main()
