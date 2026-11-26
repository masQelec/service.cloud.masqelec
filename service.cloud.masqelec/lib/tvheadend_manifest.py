# -*- coding: utf-8 -*-
"""Manifiesto de distribucion Tvheadend.

Sin red, Kodi, rclone ni operaciones de instalacion.
La compatibilidad debe estar autorizada explicitamente.
"""

import json
import re

from dataclasses import dataclass
from lib import tvheadend_platform as platform


ADDON_ID = "service.tvheadend43"
SCHEMA = 1

MAX_MANIFEST_BYTES = 65536
MAX_PACKAGE_BYTES = 100 * 1024 * 1024

SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")

ADDON_VERSION_PATTERN = re.compile(
    r"(?:0|[1-9][0-9]{0,3})"
    r"\.(?:0|[1-9][0-9]{0,3})"
    r"\.(?:0|[1-9][0-9]{0,3})"
)


class ManifestError(ValueError):
    """Manifiesto invalido o paquete no autorizado."""


@dataclass(frozen=True)
class Package:
    target: str
    version: str
    path: str
    size: int
    sha256: str
    validated_builds: tuple


@dataclass(frozen=True)
class Manifest:
    kodi_major: int
    packages: tuple


def _require(condition, code):
    if not condition:
        raise ManifestError(code)


def _unique_object(pairs):
    result = {}

    for key, value in pairs:

        if key in result:
            raise ManifestError("DUPLICATE_JSON_KEY")

        result[key] = value

    return result


def _matches(pattern, value):
    return (
        type(value) is str
        and pattern.fullmatch(value) is not None
    )


def _parse_package(raw):

    _require(
        isinstance(raw, dict),
        "INVALID_PACKAGE",
    )

    _require(
        set(raw) == {
            "target", "version", "path",
            "size", "sha256", "validated_builds",
        },
        "INVALID_PACKAGE_FIELDS",
    )

    target = raw["target"]

    _require(
        type(target) is str
        and target in platform.SUPPORTED_ARCHITECTURES,
        "UNSUPPORTED_TARGET",
    )

    version = raw["version"]

    _require(
        _matches(ADDON_VERSION_PATTERN, version),
        "INVALID_ADDON_VERSION",
    )

    expected_path = (
        f"pvr/tvheadend/{target}/"
        f"{ADDON_ID}-{version}.zip"
    )

    _require(
        raw["path"] == expected_path,
        "INVALID_PACKAGE_PATH",
    )

    size = raw["size"]

    _require(
        type(size) is int
        and 0 < size <= MAX_PACKAGE_BYTES,
        "INVALID_PACKAGE_SIZE",
    )

    _require(
        _matches(SHA256_PATTERN, raw["sha256"]),
        "INVALID_PACKAGE_SHA256",
    )

    builds = raw["validated_builds"]

    _require(
        isinstance(builds, list)
        and len(builds) <= 128,
        "INVALID_COMPATIBILITY_LIST",
    )

    validated = []

    for item in builds:

        _require(
            isinstance(item, dict)
            and set(item) == {"version_id", "build"},
            "INVALID_COMPATIBILITY_ENTRY",
        )

        _require(
            _matches(
                platform.VERSION_PATTERN,
                item["version_id"]
            ),
            "INVALID_COMPATIBILITY_VERSION",
        )

        _require(
            _matches(
                platform.VALUE_PATTERN,
                item["build"]
            )
            and len(item["build"]) <= 128,
            "INVALID_COMPATIBILITY_BUILD",
        )

        identity = (
            item["version_id"],
            item["build"],
        )

        _require(
            identity not in validated,
            "DUPLICATE_COMPATIBILITY_ENTRY",
        )

        validated.append(identity)

    return Package(
        target=target,
        version=version,
        path=expected_path,
        size=size,
        sha256=raw["sha256"],
        validated_builds=tuple(validated),
    )


def parse_manifest(raw, kodi_major):

    _require(
        type(raw) is bytes,
        "INVALID_MANIFEST_INPUT",
    )

    _require(
        0 < len(raw) <= MAX_MANIFEST_BYTES,
        "INVALID_MANIFEST_SIZE",
    )

    _require(
        type(kodi_major) is int
        and 1 <= kodi_major <= 99,
        "INVALID_KODI_MAJOR",
    )

    try:
        data = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique_object,
        )

    except ManifestError:
        raise

    except (
        ValueError,
        UnicodeError,
        RecursionError,
    ):
        raise ManifestError(
            "INVALID_MANIFEST_JSON"
        ) from None

    _require(
        isinstance(data, dict)
        and set(data) == {
            "schema", "addon_id",
            "kodi_major", "packages",
        },
        "INVALID_MANIFEST_FIELDS",
    )

    _require(
        type(data["schema"]) is int
        and data["schema"] == SCHEMA,
        "UNSUPPORTED_MANIFEST_SCHEMA",
    )

    _require(
        data["addon_id"] == ADDON_ID,
        "WRONG_ADDON_ID",
    )

    _require(
        type(data["kodi_major"]) is int
        and data["kodi_major"] == kodi_major,
        "KODI_MAJOR_MISMATCH",
    )

    entries = data["packages"]

    _require(
        isinstance(entries, list)
        and 0 < len(entries) <= len(
            platform.SUPPORTED_ARCHITECTURES
        ),
        "INVALID_PACKAGE_LIST",
    )

    packages = tuple(
        _parse_package(item)
        for item in entries
    )

    targets = [item.target for item in packages]

    _require(
        len(set(targets)) == len(targets),
        "DUPLICATE_PACKAGE_TARGET",
    )

    return Manifest(
        kodi_major=kodi_major,
        packages=packages,
    )


def select_package(manifest, device):

    _require(
        isinstance(manifest, Manifest)
        and isinstance(device, platform.Platform),
        "INVALID_SELECTION_INPUT",
    )

    for package in manifest.packages:

        if package.target != device.target:
            continue

        identity = (
            device.coreelec_version,
            device.coreelec_build,
        )

        _require(
            identity in package.validated_builds,
            "COREELEC_BUILD_NOT_VALIDATED",
        )

        return package

    raise ManifestError("NO_COMPATIBLE_TARGET")
