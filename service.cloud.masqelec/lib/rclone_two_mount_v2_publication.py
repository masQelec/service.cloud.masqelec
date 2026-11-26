# -*- coding: utf-8 -*-
"""Bounded, non-secret preflight for the published encrypted v2 MQC2 route.

Returns False on HTTP errors, redirects, absent/oversized/empty payloads,
unknown branches or timeouts. This is only an availability check; the
existing MQC2 verifier must still authenticate/decrypt the payload.
"""
import urllib.error
import urllib.request

from lib import constants
from lib import cloud_version_routes as cloud_routes
from lib import rclone_two_mount_config_routes as routes

MAX_BODY = 8 * 1024 * 1024


def available(open_url=None):
    if not cloud_routes.rclone_transport_branch_allowed(constants.CLOUD_BRANCH):
        return False
    base = constants.CLOUD_RAW_BASE
    if not cloud_routes.rclone_transport_base_matches(
            constants.CLOUD_BRANCH, base):
        return False
    try:
        url = routes.remote_url_for_mount_mode(base, "active")
        if open_url is None:
            opener = urllib.request.urlopen
        else:
            opener = open_url
        # Strict upper bound; never log / parse token-bearing content.
        request = urllib.request.Request(url, headers={
            "User-Agent": "masqelec-two-mount-preflight"
        })
        with opener(request, timeout=8) as response:
            code = response.getcode()
            resolved = response.geturl()
            if code != 200 or resolved != url:
                return False
            length = response.headers.get("Content-Length")
            if length is not None and (not length.isdigit()
                                      or not 0 < int(length) <= MAX_BODY):
                return False
            raw = response.read(MAX_BODY + 1)
            return isinstance(raw, bytes) and 0 < len(raw) <= MAX_BODY
    except (OSError, ValueError, TypeError, urllib.error.URLError):
        return False
