# -*- coding: utf-8 -*-
"""Inicializacion cloud sin Kodi real ni red."""

import ast
import json
import unittest

from pathlib import Path
from types import SimpleNamespace

from lib import cloud_version_routes as cloud


ROOT = Path(__file__).resolve().parents[1]

DEVELOP_BASE = (
    "https://raw.githubusercontent.com/"
    "masQelec/cloud.masqelec/develop"
)


def config(enabled=True, branch=None, base=None):
    return SimpleNamespace(
        CLOUD_VERSION_ROUTING_ENABLED=enabled,
        CLOUD_BRANCH=branch,
        CLOUD_RAW_BASE=base,
    )


def rpc_reply(major):
    return json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "version": {"major": major}
        }
    })


class CloudBootstrapTests(unittest.TestCase):

    def test_disabled_blocks_without_rpc(self):
        cfg = config(False, "develop", DEVELOP_BASE)

        def forbidden(*args):
            self.fail("RPC must not be called")

        with self.assertRaisesRegex(
            cloud.CloudVersionError,
            "^INVALID_ROUTING_FLAG$",
        ):
            cloud.initialize_runtime_route(cfg, forbidden)

    def test_enabled_initializes_kodi_21(self):
        cfg = config()

        result = cloud.initialize_runtime_route(
            cfg, lambda raw: rpc_reply(21)
        )

        self.assertEqual(
            result,
            ("21", cloud.raw_base_for_branch("21")),
        )

        self.assertEqual(cfg.CLOUD_BRANCH, "21")
        self.assertEqual(cfg.CLOUD_RAW_BASE, result[1])

    def test_rpc_failure_keeps_route_unresolved(self):
        cfg = config()

        with self.assertRaises(cloud.CloudVersionError):
            cloud.initialize_runtime_route(
                cfg, lambda raw: "invalid"
            )

        self.assertIsNone(cfg.CLOUD_BRANCH)
        self.assertIsNone(cfg.CLOUD_RAW_BASE)

    def test_session_route_cannot_change(self):
        cfg = config()

        cloud.initialize_runtime_route(
            cfg, lambda raw: rpc_reply(21)
        )

        # Repetir la misma ruta es seguro.
        cloud.initialize_runtime_route(
            cfg, lambda raw: rpc_reply(21)
        )

        with self.assertRaisesRegex(
            cloud.CloudVersionError,
            "^CLOUD_ROUTE_ALREADY_INITIALIZED$",
        ):
            cloud.initialize_runtime_route(
                cfg, lambda raw: rpc_reply(22)
            )

        self.assertEqual(cfg.CLOUD_BRANCH, "21")

    def test_invalid_flag_or_legacy_route_blocked(self):
        for cfg in (
            config(None),
            config(1),
            config(False),
            config(False, "develop", "https://bad"),
            config(False, "master", DEVELOP_BASE),
        ):
            with self.subTest(cfg=cfg):
                with self.assertRaises(
                    cloud.CloudVersionError
                ):
                    cloud.initialize_runtime_route(
                        cfg, None
                    )

    def test_constants_can_load_before_kodi(self):
        source = (
            ROOT / "lib/constants.py"
        ).read_text(encoding="utf-8")

        tree = ast.parse(source)

        # Las constantes no dependen de Kodi.
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for name in node.names:
                    self.assertFalse(
                        name.name.startswith("xbmc")
                    )

            if isinstance(node, ast.ImportFrom):
                self.assertFalse(
                    (node.module or "").startswith("xbmc")
                )

        # Simular la futura activacion sin modificar disco.
        source = source.replace(
            "CLOUD_VERSION_ROUTING_ENABLED = False",
            "CLOUD_VERSION_ROUTING_ENABLED = True",
            1,
        )

        namespace = {}

        exec(
            compile(source, "constants_test", "exec"),
            namespace,
        )

        self.assertIsNone(namespace["CLOUD_BRANCH"])
        self.assertIsNone(namespace["CLOUD_RAW_BASE"])

    def test_bootstrap_precedes_functional_imports(self):
        source = (
            ROOT / "service.py"
        ).read_text(encoding="utf-8")

        tree = ast.parse(source)

        bootstrap = []

        for node in tree.body:
            if isinstance(node, ast.Try):
                for child in ast.walk(node):
                    if (
                        isinstance(child, ast.Call)
                        and isinstance(
                            child.func, ast.Attribute
                        )
                        and child.func.attr ==
                            "initialize_runtime_route"
                    ):
                        bootstrap.append(node.lineno)

        self.assertEqual(len(bootstrap), 1)

        for node in tree.body:
            if not isinstance(node, ast.ImportFrom):
                continue

            if node.module == "lib":
                names = {
                    name.name for name in node.names
                }

                if names <= {
                    "constants", "cloud_version_routes"
                }:
                    continue

            if (node.module or "").startswith("lib"):
                self.assertGreater(
                    node.lineno, bootstrap[0]
                )


if __name__ == "__main__":
    unittest.main()
