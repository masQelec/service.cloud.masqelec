# -*- coding: utf-8 -*-
"""Selección de rutas cloud por versión principal de Kodi.

Sin red, sin escrituras, sin importaciones de Kodi.
La selección de rama no autoriza operaciones remotas.
"""

CLOUD_OWNER = "masQelec"
CLOUD_REPO = "cloud.masqelec"

# Ramas de distribución validadas para operaciones rclone.
# Ampliar únicamente después de superar las pruebas.
RCLONE_RELEASE_BRANCHES = frozenset({"21"})


class CloudVersionError(ValueError):
    """No se puede determinar una ruta cloud segura."""


def branch_from_version(version):
    """Obtiene la rama desde un diccionario de versión Kodi."""

    if not isinstance(version, dict):
        raise CloudVersionError("INVALID_KODI_VERSION")

    major = version.get("major")

    if type(major) is not int:
        raise CloudVersionError("INVALID_KODI_MAJOR")

    if not 1 <= major <= 99:
        raise CloudVersionError("INVALID_KODI_MAJOR")

    return str(major)


def resolve_branch(version_provider):
    """Consulta un proveedor de versión inyectado."""

    if not callable(version_provider):
        raise CloudVersionError("INVALID_VERSION_PROVIDER")

    try:
        version = version_provider()
    except Exception:
        raise CloudVersionError(
            "KODI_VERSION_UNAVAILABLE"
        ) from None

    return branch_from_version(version)


def valid_version_branch(branch):
    """Acepta exclusivamente ramas numéricas canónicas."""

    return (
        type(branch) is str
        and branch.isascii()
        and branch.isdecimal()
        and 1 <= len(branch) <= 2
        and branch[0] != "0"
    )


def raw_base_for_branch(branch):
    """Construye la URL RAW del repositorio autorizado."""

    if not valid_version_branch(branch):
        raise CloudVersionError("INVALID_CLOUD_BRANCH")

    return (
        "https://raw.githubusercontent.com/"
        f"{CLOUD_OWNER}/{CLOUD_REPO}/{branch}"
    )


def rclone_release_branch_allowed(branch):
    """Comprueba compatibilidad de rama.

    No sustituye las autorizaciones MASTER/CLIENTE,
    los flags de release ni las validaciones MQC2.
    """

    return (
        valid_version_branch(branch)
        and branch in RCLONE_RELEASE_BRANCHES
    )


def rclone_transport_branch_allowed(branch):
    """Solo ramas numericas de distribucion validadas."""
    return rclone_release_branch_allowed(branch)


def rclone_transport_base_matches(branch, base):
    if not rclone_transport_branch_allowed(branch):
        return False

    expected = (
        "https://raw.githubusercontent.com/"
        f"{CLOUD_OWNER}/{CLOUD_REPO}/{branch}"
    )

    return type(base) is str and base == expected


def route_from_kodi_rpc(rpc_call):
    """Resuelve rama y URL usando JSON-RPC interno de Kodi.

    No importa xbmc ni otros modulos del addon.
    No selecciona una rama alternativa ante errores.
    """
    import json

    if not callable(rpc_call):
        raise CloudVersionError("INVALID_RPC_PROVIDER")

    request = {
        "jsonrpc": "2.0",
        "method": "Application.GetProperties",
        "params": {"properties": ["version"]},
        "id": 1,
    }

    try:
        response = json.loads(
            rpc_call(json.dumps(request))
        )

        if (
            not isinstance(response, dict)
            or response.get("jsonrpc") != "2.0"
            or type(response.get("id")) is not int
            or response["id"] != 1
            or "error" in response
        ):
            raise ValueError("Invalid RPC response")

        result = response["result"]

        if not isinstance(result, dict):
            raise ValueError("Invalid RPC result")

        version = result["version"]

    except Exception:
        raise CloudVersionError(
            "KODI_VERSION_UNAVAILABLE"
        ) from None

    branch = branch_from_version(version)

    return branch, raw_base_for_branch(branch)


def initialize_runtime_route(config, rpc_call):
    """Inicializa las rutas antes de importar consumidores.

    La configuracion queda fijada durante toda la sesion.
    Una version desconocida nunca selecciona otra rama.
    """

    enabled = getattr(
        config, "CLOUD_VERSION_ROUTING_ENABLED", None
    )

    current = (
        config.CLOUD_BRANCH,
        config.CLOUD_RAW_BASE,
    )

    if enabled is not True:
        raise CloudVersionError("INVALID_ROUTING_FLAG")

    candidate = route_from_kodi_rpc(rpc_call)

    if current != (None, None) and current != candidate:
        raise CloudVersionError("CLOUD_ROUTE_ALREADY_INITIALIZED")

    config.CLOUD_BRANCH = candidate[0]
    config.CLOUD_RAW_BASE = candidate[1]

    return candidate
