import ast
import io
import json
import unittest
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from unittest.mock import Mock


class HttpResourceTests(unittest.TestCase):

    def setUp(self):

        path = (
            Path(__file__).resolve().parents[1]
            / "lib/pvr_http.py"
        )

        tree = ast.parse(path.read_text())

        names = {
            "_tvh_api_get",
            "_tvh_api_post_form",
            "_tvh_api_get_json",
        }

        selected = [
            node for node in tree.body
            if isinstance(node, ast.FunctionDef)
            and node.name in names
        ]

        self.assertEqual(
            {node.name for node in selected},
            names,
        )

        self.opener = Mock()

        self.ns = {
            "json": json,
            "urllib": urllib,
            "TVH_HTTP_PORT": 9981,
            "UA": "test-agent",
            "_tvh_urlopen": self.opener,
            "_tvh_get_http_auth": lambda: ("", ""),
        }

        module = ast.Module(
            body=selected,
            type_ignores=[],
        )

        exec(
            compile(module, str(path), "exec"),
            self.ns,
        )

    def error(self, code):

        body = io.BytesIO(b"synthetic error")

        error = urllib.error.HTTPError(
            "http://localhost/api/test",
            code,
            "synthetic",
            {},
            body,
        )

        self.opener.side_effect = error

        return body

    def test_get_404_closed(self):

        body = self.error(404)

        result = self.ns["_tvh_api_get"](
            "status/activity"
        )

        self.assertEqual(
            result,
            (False, 404, "synthetic error"),
        )

        self.assertTrue(body.closed)

    def test_get_json_404_closed(self):

        body = self.error(404)

        result = self.ns["_tvh_api_get_json"](
            "status/activity"
        )

        self.assertEqual(
            result,
            (False, 404, None, "synthetic error"),
        )

        self.assertTrue(body.closed)

    def test_post_401_closed(self):

        body = self.error(401)

        result = self.ns["_tvh_api_post_form"](
            "config/save",
            {"test": "value"},
        )

        self.assertEqual(
            result,
            (False, 401, "synthetic error"),
        )

        self.assertTrue(body.closed)

    def test_get_failed_read_closed(self):

        class BrokenBody(io.BytesIO):

            def read(self, *args):

                raise OSError("read failed")

        body = BrokenBody(b"test")

        self.opener.side_effect = (
            urllib.error.HTTPError(
                "http://localhost/api/test",
                500,
                "synthetic",
                {},
                body,
            )
        )

        result = self.ns["_tvh_api_get"](
            "status/activity"
        )

        self.assertFalse(result[0])
        self.assertTrue(body.closed)

    def test_post_failed_read_closed(self):

        class BrokenBody(io.BytesIO):

            def read(self, *args):

                raise OSError("read failed")

        body = BrokenBody(b"test")

        self.opener.side_effect = (
            urllib.error.HTTPError(
                "http://localhost/api/test",
                500,
                "synthetic",
                {},
                body,
            )
        )

        result = self.ns["_tvh_api_post_form"](
            "config/save",
            {"test": "value"},
        )

        self.assertFalse(result[0])
        self.assertTrue(body.closed)


if __name__ == "__main__":
    unittest.main()
