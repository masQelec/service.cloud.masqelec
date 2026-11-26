# -*- coding: utf-8 -*-
"""Non-secret published encrypted v2 config existence gate tests."""
import io
import unittest
from unittest import mock

from lib import rclone_two_mount_v2_publication as published


class FakeResponse:
    def __init__(self, code=200, url=None, payload=b"encrypted-mqc2",
                 length=None):
        self.code = code
        self.url = url
        self.payload = payload
        self.headers = {}
        if length is not None:
            self.headers["Content-Length"] = length
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def getcode(self):
        return self.code
    def geturl(self):
        return self.url
    def read(self, size):
        return self.payload[:size]


class PublicationTests(unittest.TestCase):
    def setUp(self):
        route_patch = mock.patch.object(
            published.constants,
            "CLOUD_RAW_BASE",
            "https://raw.githubusercontent.com/"
            "masQelec/cloud.masqelec/21"
        )

        route_patch.start()
        self.addCleanup(route_patch.stop)

    def test_published_bytes_available(self):
        with mock.patch.object(published.constants, "CLOUD_BRANCH", "21"):
            def opener(req, timeout):
                self.assertEqual(timeout, 8)
                self.assertTrue(req.full_url.endswith(
                    "/rclone/rclone-v2.conf.crypt"))
                return FakeResponse(url=req.full_url)
            self.assertTrue(published.available(opener))

    def test_missing_config_and_network_fault_block(self):
        with mock.patch.object(published.constants, "CLOUD_BRANCH", "21"):
            self.assertFalse(published.available(
                lambda req, timeout: FakeResponse(
                    code=404, url=req.full_url)))
            self.assertFalse(published.available(
                lambda req, timeout: FakeResponse(
                    url=req.full_url, payload=b"")))
            self.assertFalse(published.available(
                lambda req, timeout: FakeResponse(
                    url=req.full_url, length="999999999999")))
            def failure(req, timeout):
                raise OSError("network unavailable")
            self.assertFalse(published.available(failure))

    def test_redirect_rejected(self):
        with mock.patch.object(published.constants, "CLOUD_BRANCH", "21"):
            self.assertFalse(published.available(
                lambda req, timeout: FakeResponse(
                    url="https://example.com/redirect", payload=b"whatever")))

    def test_invalid_branch_never_connects(self):
        with mock.patch.object(published.constants, "CLOUD_BRANCH", "main"):
            self.assertFalse(published.available(
                lambda *args, **kwargs: self.fail("must not connect")))

    def test_invalid_route_rejected(self):
        with mock.patch.object(published.constants, "CLOUD_BRANCH", "21"), \
             mock.patch.object(
                 published.constants, "CLOUD_RAW_BASE", "http://bad/"):
            self.assertFalse(published.available(
                lambda *args, **kwargs: self.fail("must not connect")))


if __name__ == "__main__":
    unittest.main()
