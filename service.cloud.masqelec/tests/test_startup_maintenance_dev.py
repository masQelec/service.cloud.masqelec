# -*- coding: utf-8 -*-
"""Regresión del mantenimiento DEVELOP sin cargar dependencias Kodi."""
import ast
import unittest
from pathlib import Path


_SERVICE = Path(__file__).resolve().parents[1] / "service.py"


def _function(name):
    module = ast.parse(_SERVICE.read_text(encoding="utf-8"))
    return next(node for node in module.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == name)


def _calls(node):
    return [
        n.func.attr if isinstance(n.func, ast.Attribute) else n.func.id
        for n in ast.walk(node)
        if isinstance(n, ast.Call)
        and isinstance(n.func, (ast.Attribute, ast.Name))
    ]


class StartupMaintenanceDevelopTests(unittest.TestCase):
    def test_startup_skips_scan_but_keeps_catalog(self):
        fn = _function("_startup_maintenance_wrapper")
        names = _calls(fn)
        self.assertNotIn("update_library_silent", names)
        self.assertIn("generate_catalog", names)
        self.assertIn("load_catalog_github", names)

    def test_periodic_scan_still_active(self):
        fn = _function("_periodic_update_worker")
        self.assertIn("update_library_silent", _calls(fn))

    def test_startup_defers_periodic_scan(self):
        fn = _function("_startup_maintenance_wrapper")
        assignments = [
            n for n in ast.walk(fn)
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "_last_update_ts"
                    for t in n.targets)
        ]
        self.assertTrue(assignments, "No se difiere el primer Scan periódico")


if __name__ == "__main__":
    unittest.main()
