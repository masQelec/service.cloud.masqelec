# -*- coding: utf-8 -*-
"""Descarga y validacion de paquetes Tvheadend.

No instala addons, extrae archivos ni controla servicios.
"""

import hashlib
import http.client
import re
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
import zlib

from contextlib import contextmanager
from pathlib import Path

from lib import cloud_version_routes as cloud
from lib import tvheadend_manifest as manifest
from lib import tvheadend_platform as platform
from lib import tvheadend_version as version


MANIFEST_PATH = "pvr/tvheadend/manifest.json"

CHUNK_SIZE = 256 * 1024
SOCKET_TIMEOUT = 30
TRANSFER_TIMEOUT = 180

MAX_ZIP_MEMBERS = 8192
MAX_UNPACKED_BYTES = 512 * 1024 * 1024


class PackageError(ValueError):
    """Descarga o paquete rechazado."""


class ManifestNotPublished(PackageError):
    """Todavia no existe una distribucion publicada."""


def _require(condition, code):
    if not condition:
        raise PackageError(code)


class NoRedirect(urllib.request.HTTPRedirectHandler):

    def redirect_request(
        self, req, fp, code, msg,
        headers, newurl
    ):
        raise PackageError("HTTP_REDIRECT_BLOCKED")


def _open(request, timeout):

    opener = urllib.request.build_opener(
        NoRedirect()
    )

    return opener.open(
        request,
        timeout=timeout,
    )


def _check_route(branch, base):

    _require(
        cloud.valid_version_branch(branch),
        "INVALID_CLOUD_BRANCH",
    )

    _require(
        base == cloud.raw_base_for_branch(branch),
        "CLOUD_BASE_MISMATCH",
    )

    return int(branch)


def _transfer(
    url, sink, limit,
    expected=None, opener=None,
    manifest_request=False,
):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "masQelec-TVHeadend-Updater/1",
            "Accept-Encoding": "identity",
        },
        method="GET",
    )

    total = 0
    started = time.monotonic()

    try:
        open_url = opener or _open

        with open_url(
            request, timeout=SOCKET_TIMEOUT
        ) as response:

            _require(
                response.geturl() == url,
                "HTTP_URL_MISMATCH",
            )

            _require(
                response.getcode() == 200,
                "INVALID_HTTP_STATUS",
            )

            encoding = response.headers.get(
                "Content-Encoding", "identity"
            )

            _require(
                encoding.lower() == "identity",
                "UNEXPECTED_CONTENT_ENCODING",
            )

            length = response.headers.get(
                "Content-Length"
            )

            declared = None

            if length is not None:

                _require(
                    re.fullmatch(
                        r"[0-9]{1,12}", length
                    ) is not None,
                    "INVALID_CONTENT_LENGTH",
                )

                declared = int(length)

                _require(
                    0 < declared <= limit,
                    "HTTP_SIZE_LIMIT",
                )

                if expected is not None:
                    _require(
                        declared == expected,
                        "HTTP_SIZE_MISMATCH",
                    )

            while True:

                _require(
                    time.monotonic() - started
                    <= TRANSFER_TIMEOUT,
                    "TRANSFER_TIMEOUT",
                )

                chunk = response.read(
                    min(
                        CHUNK_SIZE,
                        limit - total + 1
                    )
                )

                if not chunk:
                    break

                total += len(chunk)

                _require(
                    total <= limit,
                    "DOWNLOAD_SIZE_LIMIT",
                )

                sink(chunk)

            _require(
                total > 0,
                "EMPTY_DOWNLOAD",
            )

            if declared is not None:
                _require(
                    total == declared,
                    "INCOMPLETE_DOWNLOAD",
                )

            if expected is not None:
                _require(
                    total == expected,
                    "DOWNLOAD_SIZE_MISMATCH",
                )

    except urllib.error.HTTPError as exc:

        code = exc.code
        exc.close()

        if manifest_request and code == 404:
            raise ManifestNotPublished(
                "MANIFEST_NOT_PUBLISHED"
            ) from None

        raise PackageError(
            "HTTP_DOWNLOAD_FAILED"
        ) from None

    except (
        OSError,
        http.client.HTTPException,
    ):
        raise PackageError(
            "DOWNLOAD_FAILED"
        ) from None

    return total


def fetch_manifest(branch, base, opener=None):

    major = _check_route(branch, base)

    raw = bytearray()

    _transfer(
        base + "/" + MANIFEST_PATH,
        raw.extend,
        manifest.MAX_MANIFEST_BYTES,
        opener=opener,
        manifest_request=True,
    )

    return manifest.parse_manifest(
        bytes(raw), major
    )


def _validate_elf(header, device):

    _require(
        len(header) >= 20
        and header[:4] == b"\x7fELF",
        "INVALID_TVHEADEND_ELF",
    )

    expected_class = {
        32: 1,
        64: 2,
    }[device.elf_bits]

    _require(
        header[4] == expected_class,
        "ELF_CLASS_MISMATCH",
    )

    _require(
        header[5] == 1 and header[6] == 1,
        "INVALID_ELF_FORMAT",
    )

    elf_type = int.from_bytes(
        header[16:18], "little"
    )

    _require(
        elf_type in (2, 3),
        "INVALID_ELF_TYPE",
    )

    machine = int.from_bytes(
        header[18:20], "little"
    )

    _require(
        machine == device.elf_machine,
        "ELF_MACHINE_MISMATCH",
    )


def validate_zip(path, package, device):
    """Valida un ZIP local sin extraer su contenido.

    Utilizable tambien en laboratorio con candidatos
    aun no autorizados. No concede permiso de instalar.
    """

    _require(
        isinstance(package, manifest.Package)
        and isinstance(device, platform.Platform),
        "INVALID_PACKAGE_INPUT",
    )

    _require(
        package.target == device.target,
        "PACKAGE_TARGET_MISMATCH",
    )

    digest = hashlib.sha256()
    total = 0

    try:
        with open(path, "rb") as stream:

            for chunk in iter(
                lambda: stream.read(CHUNK_SIZE),
                b"",
            ):

                total += len(chunk)

                _require(
                    total <= package.size,
                    "PACKAGE_SIZE_MISMATCH",
                )

                digest.update(chunk)

            _require(
                total == package.size,
                "PACKAGE_SIZE_MISMATCH",
            )

            _require(
                digest.hexdigest() == package.sha256,
                "PACKAGE_SHA256_MISMATCH",
            )

            stream.seek(0)

            with zipfile.ZipFile(stream) as archive:

                infos = archive.infolist()

                _require(
                    0 < len(infos) <= MAX_ZIP_MEMBERS,
                    "INVALID_ZIP_MEMBER_COUNT",
                )

                paths = {}
                unpacked = 0

                for info in infos:

                    name = info.filename
                    canonical = name.rstrip("/")
                    parts = canonical.split("/")

                    _require(
                        info.orig_filename == name
                        and "\\" not in name
                        and ":" not in name
                        and not any(
                            ord(c) < 32 or ord(c) == 127
                            for c in name
                        )
                        and all(
                            part not in ("", ".", "..")
                            for part in parts
                        )
                        and parts[0] == manifest.ADDON_ID,
                        "UNSAFE_ZIP_PATH",
                    )

                    _require(
                        canonical not in paths,
                        "DUPLICATE_ZIP_PATH",
                    )

                    is_dir = info.is_dir()
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)

                    _require(
                        kind in (
                            0,
                            stat.S_IFDIR if is_dir
                            else stat.S_IFREG,
                        )
                        and not mode & 0o7000,
                        "UNSAFE_ZIP_FILE_TYPE",
                    )

                    _require(
                        not info.flag_bits & 1,
                        "ENCRYPTED_ZIP_MEMBER",
                    )

                    _require(
                        info.compress_type in (
                            zipfile.ZIP_STORED,
                            zipfile.ZIP_DEFLATED,
                        ),
                        "UNSUPPORTED_ZIP_COMPRESSION",
                    )

                    _require(
                        len(parts) > 1 or is_dir,
                        "INVALID_ZIP_ROOT",
                    )

                    if is_dir:
                        _require(
                            info.file_size == 0,
                            "INVALID_ZIP_DIRECTORY",
                        )

                    paths[canonical] = is_dir

                    unpacked += info.file_size

                    _require(
                        unpacked <= MAX_UNPACKED_BYTES,
                        "ZIP_UNPACKED_SIZE_LIMIT",
                    )

                # Impide que un archivo sea tambien
                # el directorio padre de otro miembro.

                for name in paths:

                    parts = name.split("/")

                    for index in range(1, len(parts)):

                        parent = "/".join(parts[:index])

                        _require(
                            paths.get(parent) is not False,
                            "ZIP_PARENT_FILE_CONFLICT",
                        )

                addon_xml = (
                    manifest.ADDON_ID + "/addon.xml"
                )

                binary = (
                    manifest.ADDON_ID + "/bin/tvheadend"
                )

                _require(
                    paths.get(addon_xml) is False,
                    "MISSING_ZIP_ADDON_XML",
                )

                _require(
                    paths.get(binary) is False,
                    "MISSING_TVHEADEND_BINARY",
                )

                _require(
                    archive.getinfo(
                        addon_xml
                    ).file_size
                    <= version.MAX_ADDON_XML_BYTES,
                    "ZIP_ADDON_XML_TOO_LARGE",
                )

                try:
                    addon_version = (
                        version.parse_installed_addon_xml(
                            archive.read(addon_xml)
                        )
                    )

                except version.VersionError:
                    raise PackageError(
                        "INVALID_ZIP_ADDON_XML"
                    ) from None

                _require(
                    addon_version == package.version,
                    "ZIP_VERSION_MISMATCH",
                )

                with archive.open(binary) as executable:

                    _validate_elf(
                        executable.read(64), device
                    )

                # Verificacion CRC de todos los miembros.
                # No se escribe ningun archivo en disco.

                _require(
                    archive.testzip() is None,
                    "ZIP_CRC_MISMATCH",
                )

                return {
                    "members": len(infos),
                    "unpacked_bytes": unpacked,
                }

    except PackageError:
        raise

    except (
        OSError,
        RuntimeError,
        ValueError,
        EOFError,
        NotImplementedError,
        zipfile.BadZipFile,
        zlib.error,
    ):
        raise PackageError(
            "INVALID_PACKAGE_ZIP"
        ) from None


@contextmanager
def stage_update(
    distribution,
    device,
    installed_version,
    branch,
    base,
    staging_parent,
    opener=None,
):
    """Entrega un ZIP verificado dentro de staging privado.

    No descarga si no hay actualizacion autorizada.
    El temporal se elimina al terminar el contexto.
    """

    major = _check_route(branch, base)

    _require(
        isinstance(distribution, manifest.Manifest)
        and distribution.kodi_major == major,
        "MANIFEST_ROUTE_MISMATCH",
    )

    decision = version.decide_update(
        distribution, device, installed_version
    )

    if decision.status != version.UPDATE_AVAILABLE:

        yield decision, None
        return

    package = decision.package

    expected_path = (
        f"pvr/tvheadend/{device.target}/"
        f"{manifest.ADDON_ID}-{package.version}.zip"
    )

    _require(
        package.path == expected_path,
        "INVALID_DOWNLOAD_PATH",
    )

    _require(
        type(package.size) is int
        and 0 < package.size
        <= manifest.MAX_PACKAGE_BYTES,
        "INVALID_PACKAGE_SIZE",
    )

    with tempfile.TemporaryDirectory(
        prefix="masqelec-tvh-",
        dir=staging_parent,
    ) as folder:

        path = Path(folder) / (
            f"{manifest.ADDON_ID}-{package.version}.zip"
        )

        with path.open("xb") as stream:

            _transfer(
                base + "/" + package.path,
                stream.write,
                package.size,
                expected=package.size,
                opener=opener,
            )

        validate_zip(path, package, device)

        yield decision, path
