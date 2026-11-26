# -*- coding: utf-8 -*-
"""Gestion de playlist independiente de Kodi, TVH y rclone."""

import gzip
import io
import os
import re
import tempfile
import zlib

from pathlib import Path
from urllib.parse import quote, urlsplit


USER_DIR = Path("/storage/.user")
PLAYLIST = USER_DIR / "playlist.m3u"
CREDENTIALS = USER_DIR / "user"

MAX_PLAYLIST = 16 * 1024 * 1024
MAX_CREDENTIALS = 64 * 1024

CUID_PATTERN = re.compile(
    r'\bCUID\s*=\s*"([^"]+)"',
    re.IGNORECASE,
)


class PlaylistError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise PlaylistError(code)


def read_limited(path, maximum):

    with Path(path).open("rb") as stream:
        data = stream.read(maximum + 1)

    require(
        len(data) <= maximum,
        "FILE_TOO_LARGE",
    )

    return data


def normalize(data):

    text = data.decode("utf-8-sig", errors="strict")

    require(
        "\x00" not in text,
        "INVALID_PLAYLIST_ENCODING",
    )

    return text.replace(
        "\r\n", "\n"
    ).replace("\r", "\n")


def read_credentials(path=CREDENTIALS):

    require(
        Path(path).is_file(),
        "CREDENTIALS_MISSING",
    )

    text = normalize(
        read_limited(path, MAX_CREDENTIALS)
    )

    result = {}

    for key in ("USER_CODE", "PASS_CODE"):

        matches = re.findall(
            rf'(?m)^\s*(?:export\s+)?{key}\s*=\s*"([^"\r\n]+)"\s*$',
            text,
        )

        require(
            len(matches) == 1,
            "INVALID_CREDENTIALS",
        )

        value = matches[0].strip()

        require(
            bool(value)
            and not any(
                ord(char) < 32 or ord(char) == 127
                for char in value
            ),
            "INVALID_CREDENTIALS",
        )

        result[key] = value

    return result


def decode_response(data, encoding=""):

    require(
        len(data) <= MAX_PLAYLIST,
        "DOWNLOAD_TOO_LARGE",
    )

    encoding = encoding.strip().lower()

    if encoding == "gzip" or data.startswith(b"\x1f\x8b"):

        with gzip.GzipFile(
            fileobj=io.BytesIO(data)
        ) as stream:

            data = stream.read(MAX_PLAYLIST + 1)

    elif encoding == "deflate":

        decoder = zlib.decompressobj()

        data = decoder.decompress(
            data, MAX_PLAYLIST + 1
        )

        require(
            decoder.eof
            and not decoder.unused_data
            and not decoder.unconsumed_tail,
            "INVALID_COMPRESSED_PLAYLIST",
        )

    else:

        require(
            encoding in ("", "identity"),
            "UNSUPPORTED_ENCODING",
        )

    require(
        len(data) <= MAX_PLAYLIST,
        "PLAYLIST_TOO_LARGE",
    )

    return normalize(data)


def download_template(base, opener=None):

    if opener is None:
        from lib.net_utils import _net_open
        opener = _net_open

    require(
        isinstance(base, str)
        and re.fullmatch(
            r"https://raw\.githubusercontent\.com/"
            r"masQelec/cloud\.masqelec/[0-9]+",
            base.rstrip("/"),
        ),
        "INVALID_CLOUD_BASE",
    )

    url = base.rstrip("/") + "/pvr/playlist.m3u"

    with opener(
        url,
        timeout=20,
        retries=1,
    ) as response:

        require(
            response.getcode() == 200,
            "PLAYLIST_HTTP_ERROR",
        )

        require(
            response.geturl() == url,
            "UNEXPECTED_PLAYLIST_REDIRECT",
        )

        encoding = response.headers.get(
            "Content-Encoding", ""
        )

        data = response.read(MAX_PLAYLIST + 1)

    return decode_response(data, encoding)


def validate_url(url):

    require(
        not any(char.isspace() for char in url),
        "INVALID_STREAM_URL",
    )

    parsed = urlsplit(url)

    require(
        parsed.scheme in ("http", "https")
        and bool(parsed.hostname),
        "INVALID_STREAM_URL",
    )

    # Valida tambien un posible puerto explicito.
    parsed.port


def render_playlist(template, credentials):

    lines = template.splitlines()

    require(
        bool(lines)
        and lines[0].strip() == "#EXTM3U",
        "INVALID_M3U_HEADER",
    )

    user = quote(
        credentials["USER_CODE"], safe=""
    )

    password = quote(
        credentials["PASS_CODE"], safe=""
    )

    output = ["#EXTM3U"]

    cuids = set()

    pending = False

    for raw in lines[1:]:

        line = raw.strip()

        if not line:
            continue

        if line.startswith("#EXTINF:"):

            require(
                not pending,
                "MISSING_STREAM_URL",
            )

            matches = CUID_PATTERN.findall(line)

            require(
                len(matches) == 1
                and bool(matches[0].strip()),
                "MISSING_OR_AMBIGUOUS_CUID",
            )

            cuid = matches[0].strip()

            require(
                cuid not in cuids,
                "DUPLICATE_CUID",
            )

            cuids.add(cuid)

            output.append(raw)

            pending = True

            continue

        if line.startswith("#"):

            require(
                not line.startswith("#EXTM3U"),
                "DUPLICATE_M3U_HEADER",
            )

            output.append(raw)
            continue

        require(
            pending,
            "ORPHAN_STREAM_URL",
        )

        require(
            line.count("USER_CODE") == 1
            and line.count("PASS_CODE") == 1,
            "INVALID_STREAM_PLACEHOLDERS",
        )

        validate_url(line)

        # Sustitucion simultanea: evita modificar
        # accidentalmente las credenciales insertadas.

        replacements = {
            "USER_CODE": user,
            "PASS_CODE": password,
        }

        rendered = re.sub(
            r"USER_CODE|PASS_CODE",
            lambda match: replacements[match.group(0)],
            line,
        )

        validate_url(rendered)

        output.append(rendered)

        pending = False

    require(
        not pending,
        "MISSING_STREAM_URL",
    )

    require(
        bool(cuids),
        "EMPTY_PLAYLIST",
    )

    result = ("\n".join(output) + "\n").encode("utf-8")

    require(
        len(result) <= MAX_PLAYLIST,
        "PLAYLIST_TOO_LARGE",
    )

    return result, len(cuids)


def install_playlist(path, data):

    path = Path(path)

    if path.is_file():

        try:
            previous = normalize(
                read_limited(path, MAX_PLAYLIST)
            ).encode("utf-8")

        except UnicodeError:
            previous = None

        if previous == data:
            return "UNCHANGED"

    path.parent.mkdir(
        mode=0o700,
        parents=True,
        exist_ok=True,
    )

    fd, temporary = tempfile.mkstemp(
        prefix=".playlist-",
        dir=path.parent,
    )

    try:

        with os.fdopen(fd, "wb") as stream:

            os.fchmod(stream.fileno(), 0o600)

            stream.write(data)
            stream.flush()

            os.fsync(stream.fileno())

        os.replace(temporary, path)

        directory_fd = os.open(
            path.parent,
            os.O_RDONLY | os.O_DIRECTORY,
        )

        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)

    finally:

        if os.path.lexists(temporary):
            os.unlink(temporary)

    return "UPDATED"


def update(
    base,
    *,
    playlist=PLAYLIST,
    credentials=CREDENTIALS,
    fetch=download_template,
):

    user = read_credentials(credentials)

    template = fetch(base)

    data, channels = render_playlist(
        template, user
    )

    status = install_playlist(
        playlist, data
    )

    return {
        "status": status,
        "channels": channels,
    }
