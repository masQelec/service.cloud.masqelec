# -*- coding: utf-8 -*-
"""Comprueba la asimilacion de la playlist local por Tvheadend.

Solo lectura. Compatible con la API legacy.
Nunca registra URLs ni credenciales.
"""

import os
import re
import stat

from collections import Counter
from urllib.parse import urlsplit


PLAYLIST = "/storage/.user/playlist.m3u"
PLAYLIST_URL = "file://" + PLAYLIST

MAX_BYTES = 16 * 1024 * 1024
MAX_ENTRIES = 20000

CONVERGED = "CONVERGED"
DEFERRED = "DEFERRED_PLAYLIST_CONVERGENCE"
UNKNOWN = "DEFERRED_PLAYLIST_CONVERGENCE_UNKNOWN"


def _read_playlist(path):

    fd = os.open(
        path,
        os.O_RDONLY | os.O_NOFOLLOW,
    )

    with os.fdopen(fd, "rb") as stream:

        info = os.fstat(stream.fileno())

        if (
            not stat.S_ISREG(info.st_mode)
            or not 0 < info.st_size <= MAX_BYTES
        ):
            raise ValueError("INVALID_PLAYLIST")

        raw = stream.read(MAX_BYTES + 1)

    if not raw or len(raw) > MAX_BYTES:
        raise ValueError("INVALID_PLAYLIST")

    return raw


def _urls(raw):

    text = raw.decode("utf-8-sig", "strict")

    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if not lines or not lines[0].startswith("#EXTM3U"):
        raise ValueError("INVALID_M3U")

    result = []

    for line in lines[1:]:

        if line.startswith("#"):
            continue

        parsed = urlsplit(line)

        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or any(c.isspace() for c in line)
        ):
            raise ValueError("INVALID_STREAM")

        result.append(line)

    if not 0 < len(result) <= MAX_ENTRIES:
        raise ValueError("INVALID_STREAM_COUNT")

    return Counter(result)


def _grid(api_get, endpoint):

    ok, code, data, _ = api_get(
        endpoint,
        query={
            "start": 0,
            "limit": MAX_ENTRIES,
        },
        timeout_s=12,
    )

    if (
        ok is not True
        or code != 200
        or not isinstance(data, dict)
    ):
        raise ValueError("GRID_UNAVAILABLE")

    entries = data.get("entries")
    total = data.get("total", data.get("totalCount"))

    if (
        not isinstance(entries, list)
        or type(total) is not int
        or not 0 <= total <= MAX_ENTRIES
        or total != len(entries)
        or not all(
            isinstance(row, dict)
            for row in entries
        )
    ):
        raise ValueError("INCOMPLETE_GRID")

    return entries


def check(api_get, playlist_path=PLAYLIST):

    try:

        original = _read_playlist(playlist_path)

        expected = _urls(original)

        count = sum(expected.values())

        networks = _grid(
            api_get, "mpegts/network/grid"
        )

        selected = [
            row for row in networks
            if row.get("url") == PLAYLIST_URL
        ]

        if len(selected) != 1:
            return UNKNOWN

        network = selected[0]

        uuid = network.get("uuid")

        if (
            not isinstance(uuid, str)
            or not re.fullmatch(r"[0-9a-f]{32}", uuid)
            or type(network.get("num_mux")) is not int
        ):
            return UNKNOWN

        if network["num_mux"] != count:
            return DEFERRED

        muxes = _grid(
            api_get, "mpegts/mux/grid"
        )

        actual = []

        identities = set()

        for row in muxes:

            network_uuid = row.get("network_uuid")

            if not isinstance(network_uuid, str):
                return UNKNOWN

            if network_uuid != uuid:
                continue

            mux_uuid = row.get("uuid")
            url = row.get("iptv_url")

            if (
                not isinstance(mux_uuid, str)
                or not re.fullmatch(
                    r"[0-9a-f]{32}", mux_uuid
                )
                or mux_uuid in identities
                or not isinstance(url, str)
                or not url
            ):
                return UNKNOWN

            identities.add(mux_uuid)

            actual.append(url)

        if _read_playlist(playlist_path) != original:
            return DEFERRED

        if Counter(actual) != expected:
            return DEFERRED

        return CONVERGED

    except Exception:

        return UNKNOWN
