# -*- coding: utf-8 -*-
"""Selección local de arquitectura rclone; el servidor NO la activa.

Un addon nuevo puede convivir con clientes antiguos. La distribución de
la versión y su activación deben ser operaciones separadas. No se escribe
estado, no se ejecuta systemctl ni se descarga contenido de red aquí.
"""
import json
import os

STATE_PATH = "/storage/.config/masqelec/rclone-mount-mode.json"
SCHEMA = 1
LAYOUT = "two-fuse-v1"
CANDIDATE_ID = "2026-11-17-two-fuse-v1"
LEGACY_SERVICES = (
    "rclone_tvshows_1.service", "rclone_tvshows_2.service",
    "rclone_videos_1.service", "rclone_videos_2.service",
)
NEW_SERVICES = ("rclone_library_1.service", "rclone_library_2.service")
BIND_SERVICES = (
    "masqelec_bind_tvshows_1.service", "masqelec_bind_tvshows_2.service",
    "masqelec_bind_videos_1.service", "masqelec_bind_videos_2.service",
)

# Una fase de ensayo jamás debe convertirse por accidente en activación.
_ALLOWED_STATES = ("prepared", "active")


def parse_state(data):
    """Analiza marcador por dispositivo; ignora metadatos no autorizados."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "strict")
    obj = json.loads(data)
    if not isinstance(obj, dict) or set(obj) != {
            "schema", "layout", "state", "candidate_id"}:
        raise ValueError("Marcador de arquitectura inválido")
    if type(obj["schema"]) is not int or obj["schema"] != SCHEMA:
        raise ValueError("Versión de marcador no admitida")
    if (obj["layout"] != LAYOUT or obj["state"] not in _ALLOWED_STATES
            or obj["candidate_id"] != CANDIDATE_ID):
        raise ValueError("Estado de arquitectura no admitido")
    return obj["state"]


def mode(feature_allowed=False, state_path=STATE_PATH):
    """Devuelve legacy/prepared/active/unsafe, sin cambiar archivos.

    En caso de marcador corrupto y función habilitada, no se considera
    el dispositivo legacy automáticamente: un operador debe revisarlo.
    """
    # Incluso con el flag deshabilitado, un dispositivo ya migrado no
    # puede reactivar los cuatro servicios legacy por accidente.
    if os.path.islink(state_path):
        return "unsafe"
    try:
        with open(state_path, "rb") as stream:
            raw = stream.read(4097)
    except FileNotFoundError:
        return "legacy"
    except OSError:
        return "unsafe"
    if len(raw) > 4096:
        return "unsafe"
    try:
        state = parse_state(raw)
    except (ValueError, TypeError, UnicodeError):
        return "unsafe"
    if state == "active" and not feature_allowed:
        return "unsafe"
    if state == "prepared" and not feature_allowed:
        return "legacy"
    return state


def managed_legacy_services(device_mode):
    """Los clientes activos NO deben volver a descargar unidades legacy."""
    if device_mode == "active":
        return ()
    if device_mode in ("legacy", "prepared"):
        return LEGACY_SERVICES
    raise ValueError("Estado inseguro: no actualizar servicios rclone")


def apply_permission(device_mode):
    """No hay ruta de activación automática en esta fase."""
    if device_mode == "legacy":
        return "continue_legacy"
    if device_mode == "prepared":
        return "stage_only"
    if device_mode == "active":
        return "already_active_do_not_restart"
    return "blocked_invalid_state"


def version_supported(bundle):
    """Compatibilidad del manifiesto SIN implicar autorización de despliegue."""
    if not isinstance(bundle, dict):
        return False
    return (type(bundle.get("schema")) is int and bundle["schema"] == SCHEMA
            and bundle.get("layout") == LAYOUT
            and bundle.get("activation") == "operator_only"
            and bundle.get("credential_source") == "local_mqc2_verified"
            and bundle.get("candidate_id") == CANDIDATE_ID)
