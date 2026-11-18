# -*- coding: utf-8 -*-
"""Contrato PURO de rutas MQC2 legacy/v2; no red, IO ni activación.

Los addons Kodi distribuidos con versiones distintas pueden consultar
rutas MQC2 distintas sin instalar dos arquitecturas de montaje en un
mismo dispositivo. Un cliente v2 NO debe retroceder silenciosamente al
endpoint legacy ante fallo OAuth.
"""

LEGACY_REMOTE_PATH = "rclone/rclone.conf.crypt"
V2_REMOTE_PATH = "rclone/rclone-v2.conf.crypt"

_READ_ROUTES = {
    "legacy": LEGACY_REMOTE_PATH,
    "prepared": LEGACY_REMOTE_PATH,
    "active": V2_REMOTE_PATH,
}


def remote_path_for_mount_mode(mode):
    """Selección estricta según estado LOCAL verificado.

    `prepared` aún utiliza los cuatro montajes antiguos; `active` implica
    seis unidades v2 sanas. Los estados corruptos y transitorios nunca
    seleccionan una ruta como fallback silencioso.
    """
    if type(mode) is not str or mode not in _READ_ROUTES:
        raise ValueError("Estado local no autorizado para MQC2")
    return _READ_ROUTES[mode]


def remote_url_for_mount_mode(base_url, mode):
    """URL de lectura, SIN descargarla; no acepta un host arbitrario."""
    if type(base_url) is not str or not base_url.startswith(
            "https://raw.githubusercontent.com/masQelec/cloud.masqelec/"):
        raise ValueError("Origen MQC2 no confiable")
    if "\n" in base_url or "\r" in base_url or "?" in base_url or "#" in base_url:
        raise ValueError("URL MQC2 inestable")
    return base_url.rstrip("/") + "/" + remote_path_for_mount_mode(mode)


def publication_destination(kind):
    """Reserva un nombre estable; NO autoriza upload.

    La publicación efectiva exige snapshot reconciliado, CAS y readback.
    """
    if kind == "legacy":
        return LEGACY_REMOTE_PATH
    if kind == "v2":
        return V2_REMOTE_PATH
    raise ValueError("Destino de publicación no autorizado")
