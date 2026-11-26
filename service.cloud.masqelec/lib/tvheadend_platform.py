# -*- coding: utf-8 -*-
"""Deteccion estricta de plataforma CoreELEC para Tvheadend.

Sin dependencias Kodi, red, rclone ni comandos externos.
No instala paquetes ni modifica archivos.
"""

import re
from dataclasses import dataclass


MAX_OS_RELEASE_BYTES = 32768

SUPPORTED_ARCHITECTURES = {
    "Amlogic-ng.arm": ("Amlogic-ng", "arm", 32, 40),
    "Amlogic-ne.aarch64": ("Amlogic-ne", "aarch64", 64, 183),
}

RELEASE_KEYS = frozenset({
    "ID",
    "VERSION_ID",
    "VERSION",
    "COREELEC_ARCH",
    "COREELEC_DEVICE",
    "LIBREELEC_ARCH",
})

VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]{0,3})"
    r"\.(?:0|[1-9][0-9]{0,3})"
    r"(?:\.(?:0|[1-9][0-9]{0,3}))?"
)

VALUE_PATTERN = re.compile(r"[A-Za-z0-9_.+-]+")


class PlatformError(ValueError):
    """Plataforma no identificada o no autorizada."""


@dataclass(frozen=True)
class Platform:
    target: str
    device: str
    architecture: str
    coreelec_version: str
    coreelec_build: str
    elf_bits: int
    elf_machine: int


def parse_os_release(text):
    """Lee exclusivamente las claves necesarias.

    No ejecuta ni interpreta contenido como shell.
    Rechaza claves relevantes duplicadas.
    """

    if not isinstance(text, str):
        raise PlatformError("INVALID_OS_RELEASE")

    if len(text.encode("utf-8")) > MAX_OS_RELEASE_BYTES:
        raise PlatformError("OS_RELEASE_TOO_LARGE")

    result = {}

    for line in text.splitlines():

        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()

        if key not in RELEASE_KEYS:
            continue

        if key in result:
            raise PlatformError("DUPLICATE_OS_RELEASE_KEY")

        value = value.strip()

        if value.startswith(("'", '"')):

            if len(value) < 2 or value[-1] != value[0]:
                raise PlatformError("INVALID_OS_RELEASE_VALUE")

            value = value[1:-1]

        if not VALUE_PATTERN.fullmatch(value):
            raise PlatformError("INVALID_OS_RELEASE_VALUE")

        result[key] = value

    return result


def detect_from_text(text):
    """Identifica el target exacto de compilacion."""

    values = parse_os_release(text)

    if values.get("ID") != "coreelec":
        raise PlatformError("UNSUPPORTED_OS")

    version = values.get("VERSION_ID", "")

    if not VERSION_PATTERN.fullmatch(version):
        raise PlatformError("INVALID_COREELEC_VERSION")

    target = values.get("COREELEC_ARCH")

    if target not in SUPPORTED_ARCHITECTURES:
        raise PlatformError("UNSUPPORTED_COREELEC_ARCH")

    device, architecture, bits, machine = (
        SUPPORTED_ARCHITECTURES[target]
    )

    if (
        "COREELEC_DEVICE" in values
        and values["COREELEC_DEVICE"] != device
    ):
        raise PlatformError("COREELEC_DEVICE_MISMATCH")

    if (
        "LIBREELEC_ARCH" in values
        and values["LIBREELEC_ARCH"] != target
    ):
        raise PlatformError("COREELEC_ARCH_MISMATCH")

    return Platform(
        target=target,
        device=device,
        architecture=architecture,
        coreelec_version=version,
        coreelec_build=values.get("VERSION", version),
        elf_bits=bits,
        elf_machine=machine,
    )


def detect(path="/etc/os-release"):
    """Lectura local acotada y sin efectos secundarios."""

    try:
        with open(path, "rb") as stream:
            raw = stream.read(MAX_OS_RELEASE_BYTES + 1)

        if len(raw) > MAX_OS_RELEASE_BYTES:
            raise PlatformError("OS_RELEASE_TOO_LARGE")

        text = raw.decode("utf-8", "strict")

    except (OSError, UnicodeError):
        raise PlatformError(
            "OS_RELEASE_UNAVAILABLE"
        ) from None

    return detect_from_text(text)
