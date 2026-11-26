# -*- coding: utf-8 -*-
"""Decision de actualizacion Tvheadend.

Solo lectura. Sin Kodi, red, rclone ni systemd.
No descarga, instala o modifica paquetes.
"""

import re
import xml.etree.ElementTree as ET

from dataclasses import dataclass
from lib import tvheadend_manifest as manifest


INSTALLED_ADDON_XML = (
    "/storage/.kodi/addons/"
    "service.tvheadend43/addon.xml"
)

MAX_ADDON_XML_BYTES = 256 * 1024

VERSION_COMPONENT = r"(?:0|[1-9][0-9]{0,3})"

VERSION_PATTERN = re.compile(
    VERSION_COMPONENT
    + r"(?:\." + VERSION_COMPONENT + r"){2,3}"
)

UPDATE_AVAILABLE = "UPDATE_AVAILABLE"
UP_TO_DATE = "UP_TO_DATE"
LOCAL_NEWER = "LOCAL_NEWER"


class VersionError(ValueError):
    """Version no identificada o metadatos invalidos."""


@dataclass(frozen=True)
class UpdateDecision:
    status: str
    installed_version: str
    available_version: str
    package: manifest.Package


def parse_version(value):
    """Normaliza tres o cuatro componentes numericos."""

    if (
        type(value) is not str
        or VERSION_PATTERN.fullmatch(value) is None
    ):
        raise VersionError("INVALID_VERSION")

    parts = tuple(
        int(part) for part in value.split(".")
    )

    return parts + (0,) * (4 - len(parts))


def compare_versions(left, right):

    a = parse_version(left)
    b = parse_version(right)

    return (a > b) - (a < b)


def parse_installed_addon_xml(raw):

    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > MAX_ADDON_XML_BYTES
    ):
        raise VersionError("INVALID_ADDON_XML_SIZE")

    try:
        text = raw.decode("utf-8-sig", "strict")

        if "<!DOCTYPE" in text or "<!ENTITY" in text:
            raise VersionError(
                "UNSAFE_ADDON_XML"
            )

        root = ET.fromstring(text)

    except (ET.ParseError, UnicodeError):
        raise VersionError(
            "INVALID_ADDON_XML"
        ) from None

    if (
        root.tag != "addon"
        or root.get("id") != manifest.ADDON_ID
    ):
        raise VersionError("WRONG_INSTALLED_ADDON")

    version = root.get("version")

    parse_version(version)

    return version


def read_installed_version(
    path=INSTALLED_ADDON_XML
):
    """Lee el addon instalado sin modificarlo."""

    try:
        with open(path, "rb") as stream:
            raw = stream.read(
                MAX_ADDON_XML_BYTES + 1
            )

    except FileNotFoundError:
        raise VersionError(
            "ADDON_NOT_INSTALLED"
        ) from None

    except OSError:
        raise VersionError(
            "ADDON_XML_UNAVAILABLE"
        ) from None

    return parse_installed_addon_xml(raw)


def decide_update(
    distribution,
    device,
    installed_version,
):
    """Selecciona exclusivamente paquetes autorizados."""

    local = parse_version(installed_version)

    package = manifest.select_package(
        distribution,
        device,
    )

    remote = parse_version(package.version)

    if remote > local:
        status = UPDATE_AVAILABLE

    elif remote == local:
        status = UP_TO_DATE

    else:
        status = LOCAL_NEWER

    return UpdateDecision(
        status=status,
        installed_version=installed_version,
        available_version=package.version,
        package=package,
    )
