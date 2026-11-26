# -*- coding: utf-8 -*-
"""
catalog_utils.py — Subida de catálogo a GitHub (ZIP + VERSION) con token cifrado

Funcionalidad:
- Master: sube catalog.zip y catalog.version a GitHub (API contents PUT).
- Orden: primero ZIP y luego VERSION.
- Control tamaño: <= 75MB raw y <= 100MB base64 (como antes).
- Token GitHub: formato MQC2 autenticado (ChaCha20-Poly1305) -> clave del dispositivo.
"""

import os
import json
import time
import base64
import hashlib
import traceback
import urllib.parse
import urllib.request
import urllib.error

from lib import log_utils
from lib import device_utils
from lib import crypto_utils
from lib import catalog_safety

# ------------------------------
# Config (preferente: constants.py)
# ------------------------------
from lib import constants

OWNER = constants.CLOUD_OWNER
REPO = constants.CLOUD_REPO
BRANCH = constants.CLOUD_BRANCH
API_BASE = (
    f"https://api.github.com/repos/{OWNER}/{REPO}/contents"
    if BRANCH else ""
)

GITHUB_TOKEN_B64 = constants.GITHUB_TOKEN_B64
SRC_DIR = getattr(constants, "SRC_DIR", "/storage/.catalog")
FILES = getattr(constants, "FILES", [
    ("catalog.zip", "catalog/catalog.zip"),
    ("catalog.version", "catalog/catalog.version"),
])

# ------------------------------
# Token GH (descifrado)
# ------------------------------
def _gh_get_plain_token():
    """
    Devuelve token GitHub en claro (str) o "" si no está disponible.
    """
    try:
        if not GITHUB_TOKEN_B64:
            return ""

        key = device_utils.get_key_from_authorized_keys()
        if not key:
            return ""

        plain = crypto_utils.decrypt(GITHUB_TOKEN_B64, key)
        if not plain:
            return ""

        if isinstance(plain, (bytes, bytearray)):
            tok = plain.decode("utf-8", "replace").strip()
        else:
            tok = str(plain).strip()

        return tok or ""
    except Exception:
        log_utils.write_log("[catalog] Error descifrando token GH:\n{}".format(traceback.format_exc()), "ERROR")
        return ""

# ------------------------------
# HTTP helpers (GitHub API)
# ------------------------------
def _req(method, url, token, payload=None, timeout=30):
    """
    Devuelve (status:int|None, body:str).
    status None = fallo de red/urllib.
    """
    try:
        headers = {
            "User-Agent": "masQelec/1.0 (+Kodi)",
            "Accept": "application/vnd.github+json",
            "Authorization": "token {}".format(token),
        }

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=float(timeout)) as r:
            raw = r.read() or b""
            body = raw.decode("utf-8", "replace")
            status = getattr(r, "status", None)
            if status is None:
                # algunos urllib devuelven code() en vez de status
                try:
                    status = int(r.getcode())
                except Exception:
                    status = None
            return status, body

    except urllib.error.HTTPError as e:
        try:
            body = (e.read() or b"").decode("utf-8", "replace")
        except Exception:
            body = str(e)
        return int(getattr(e, "code", 0) or 0), body

    except Exception:
        return None, traceback.format_exc()


def _get_remote_sha(token, path):
    """
    Obtiene SHA remoto (si existe) para poder hacer update (PUT con sha).
    """
    try:
        if not API_BASE:
            return None

        path_enc = urllib.parse.quote(path, safe="/")
        url = "{}/{}?ref={}".format(API_BASE, path_enc, urllib.parse.quote(BRANCH, safe=""))
        status, body = _req("GET", url, token, payload=None)
        if status != 200:
            return None
        obj = json.loads(body or "{}")
        sha = obj.get("sha")
        return sha or None
    except Exception:
        return None


# ------------------------------
# Uploader (igual funcionalidad que el anterior)
# ------------------------------
def _upload_file(token, src_path, dst_path):
    if not os.path.exists(src_path):
        log_utils.write_log("No existe {}".format(src_path), "ERROR")
        return False

    size = os.path.getsize(src_path)
    if size <= 0:
        log_utils.write_log("Archivo vacío: {}".format(src_path), "ERROR")
        return False

    if size > 75 * 1024 * 1024:
        log_utils.write_log("Archivo demasiado grande: {}".format(src_path), "ERROR")
        return False

    raw = open(src_path, "rb").read()
    b64 = base64.b64encode(raw).decode("ascii")

    if len(b64) > 100 * 1024 * 1024:
        log_utils.write_log("Payload base64 excesivo: {}".format(dst_path), "ERROR")
        return False

    sha_local = hashlib.sha256(raw).hexdigest()[:12]
    msg = "Update {} ({})".format(dst_path, sha_local)

    if not API_BASE:
        log_utils.write_log("API_BASE no configurado; no se puede subir {}".format(dst_path), "ERROR")
        return False

    path_enc = urllib.parse.quote(dst_path, safe="/")
    url = "{}/{}".format(API_BASE, path_enc)

    payload = {
        "message": msg,
        "content": b64,
        "branch": BRANCH,
    }

    sha_remote = _get_remote_sha(token, dst_path)
    if sha_remote:
        payload["sha"] = sha_remote

    status, body = _req("PUT", url, token, payload)
    if status is None:
        log_utils.write_log("PUT sin respuesta (red) {}".format(dst_path), "ERROR")
        return False

    if status in (200, 201):
        return True

    if status in (409, 422):
        log_utils.write_log("Conflicto SHA en {}, reintentando".format(dst_path), "WARNING")
        payload["sha"] = _get_remote_sha(token, dst_path)
        status, body = _req("PUT", url, token, payload)
        if status in (200, 201):
            return True

    # recortar body para no spamear
    body_short = (body or "").strip()
    if len(body_short) > 400:
        body_short = body_short[:400] + "..."
    log_utils.write_log("PUT falló {} ({}): {}".format(dst_path, status, body_short), "ERROR")
    return False


def load_catalog_github():
    """
    Sube catálogo a GitHub:
    - SOLO si existen catalog.zip y catalog.version en SRC_DIR
    - Primero catalog.zip
    - Luego catalog.version
    """
    zip_path = os.path.join(SRC_DIR, "catalog.zip")
    ver_path = os.path.join(SRC_DIR, "catalog.version")

    have_zip = os.path.isfile(zip_path)
    have_ver = os.path.isfile(ver_path)

    # Regla: si NO hay ZIP => no hay cambios (generate_catalog lo omitió)
    if not have_zip:
        log_utils.write_log("[catalog_uploader] Sin cambios: no existe catalog.zip -> NO se sube.", "INFO")
        return True

    # Si hay ZIP pero no version => eso sí es inconsistente
    if not have_ver:
        log_utils.write_log("[catalog_uploader] Estado inconsistente: zip=True version=False. Abortando subida.", "ERROR")
        return False

    # Nunca publicar ZIP/version incongruentes, ni reintentar archivos
    # incompletos de un arranque anterior.
    try:
        with open(ver_path, "r", encoding="utf-8") as f:
            version_text = f.read()
        checked_count = catalog_safety.verify_zip_manifest(zip_path, version_text)
        log_utils.write_log(
            "[catalog_uploader] ZIP y manifest verificados: {} STRM".format(checked_count), "INFO"
        )
    except Exception as exc:
        log_utils.write_log(
            "[catalog_uploader] ZIP/version inválidos; subida bloqueada: {}".format(exc),
            "ERROR",
        )
        return False

    # Ya sabemos que hay algo real que subir -> ahora sí exigimos token
    token = _gh_get_plain_token()
    if not token:
        log_utils.write_log("Token GitHub no disponible, abortando subida", "ERROR")
        return False

    # Orden fijo: ZIP primero, VERSION después. En fallo del ZIP,
    # queda prohibido publicar una VERSION nueva.
    for fname, dst in FILES:
        src = os.path.join(SRC_DIR, fname)

        # Aquí debería existir sí o sí; si no, error real
        if not os.path.isfile(src):
            log_utils.write_log("[catalog_uploader] Falta fichero requerido: {}".format(src), "ERROR")
            return False

        log_utils.write_log("Subiendo {} -> {}".format(src, dst), "INFO")
        if not _upload_file(token, src, dst):
            log_utils.write_log("Fallo subiendo {}; no se publicarán más archivos".format(dst), "ERROR")
            return False
        log_utils.write_log("{} subido correctamente".format(dst), "INFO")

    # La ausencia de ZIP representa 'sin publicación pendiente'.
    # En caso de error en GitHub, el ZIP se conserva para reintentar.
    try:
        os.remove(zip_path)
    except OSError as exc:
        log_utils.write_log(
            "[catalog_uploader] Publicado, pero no se pudo retirar ZIP local: {}".format(exc),
            "WARNING",
        )
    return True


