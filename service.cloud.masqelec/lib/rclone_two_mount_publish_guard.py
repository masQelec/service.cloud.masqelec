# -*- coding: utf-8 -*-
"""Transporte MQC2 con CAS ESTRICTO para una futura publicación OAuth v2.

NO está conectado a service.py ni al worker. GET y PUT dependen de un
callback HTTP explícito; se desaconseja cualquier uso con mounts activos
hasta completar la revalidación interproceso. No hay reintentos de 409.
"""
import base64
import binascii
import hashlib
import json
import re

from lib import chacha_pure
from lib import rclone_token_policy as policy

REMOTE_PATH = "rclone/rclone.conf.crypt"
MAX_ENCRYPTED_BYTES = 2 * 1024 * 1024
_SHA = re.compile(r"[a-f0-9]{40}\Z")


def git_blob_sha(payload):
    if not isinstance(payload, bytes):
        raise TypeError("Se requiere blob binario")
    return hashlib.sha1(
        b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    ).hexdigest()


def decode_remote_contents(response, key):
    """Verifica SHA del blob Git y descifra el contenido MQC2 autenticado.

    response es el cuerpo de GitHub contents GET, no una respuesta de
    listado, ni una URL raw sin versión. No registra su contenido.
    """
    if isinstance(response, (str, bytes)):
        response = json.loads(response)
    if not isinstance(response, dict):
        raise ValueError("Respuesta GitHub inválida")
    if response.get("encoding") != "base64":
        raise ValueError("GitHub no entregó base64")
    sha = response.get("sha")
    if not isinstance(sha, str) or not _SHA.fullmatch(sha):
        raise ValueError("SHA GitHub inválido")
    encoded = response.get("content")
    if not isinstance(encoded, str) or len(encoded) > 4 * MAX_ENCRYPTED_BYTES:
        raise ValueError("Payload GH excesivo")
    try:
        # GitHub introduce saltos de línea en el base64 de contents.
        encrypted = base64.b64decode(
            "".join(encoded.splitlines()), validate=True
        )
    except (ValueError, binascii.Error):
        raise ValueError("Base64 GH inválido")
    if not 0 < len(encrypted) <= MAX_ENCRYPTED_BYTES:
        raise ValueError("Archivo MQC2 remoto inválido")
    if git_blob_sha(encrypted) != sha:
        raise ValueError("SHA GH no corresponde a MQC2")
    plain = chacha_pure.decrypt_v2(encrypted, key)
    if not 0 < len(plain) <= 1024 * 1024:
        raise ValueError("Contenido MQC2 no válido")
    policy.validate_master_layout(plain)
    return {"sha": sha, "canonical": plain}


def encode_candidate(candidate, key):
    """Genera bytes cifrados sin subirlos. Compatible con CLIENTES legacy."""
    policy.validate_master_layout(candidate)
    if len(candidate) > 1024 * 1024:
        raise ValueError("Candidato de configuración demasiado grande")
    encrypted = (chacha_pure.encrypt_v2(candidate, key) + "\n").encode("ascii")
    if len(encrypted) > MAX_ENCRYPTED_BYTES:
        raise ValueError("Candidato cifrado excesivo")
    return encrypted


def strict_put(token, encrypted, expected_sha, request, *,
               release_authorized=False, sources_revalidated=False,
               remote_authenticated=False):
    """Una sola petición PUT GitHub, con SHA previo, NUNCA retry 409/422.

    Los tres permisos deben proceder de comprobaciones independientes:
    1. autorización explícita; 2. fuentes idénticas tras el sondeo; y
    3. mismo snapshot MQC2 autenticado asociado al SHA esperado.
    Devuelve estado; incluso 200 exige volver a leer GitHub.
    """
    if not (release_authorized is True and
            sources_revalidated is True and
            remote_authenticated is True):
        return "blocked"
    if not isinstance(token, str) or not token:
        return "no_token"
    if not isinstance(encrypted, bytes) or not (
            0 < len(encrypted) <= MAX_ENCRYPTED_BYTES):
        raise ValueError("Blob cifrado inválido")
    if not isinstance(expected_sha, str) or not _SHA.fullmatch(expected_sha):
        raise ValueError("SHA esperado inválido")
    if not callable(request):
        raise ValueError("Transporte explícito requerido")
    new_sha = git_blob_sha(encrypted)
    payload = {
        "message": "OAuth v2 snapshot verification",
        "branch": "develop",
        "sha": expected_sha,
        "content": base64.b64encode(encrypted).decode("ascii"),
    }
    status, response = request(token, REMOTE_PATH, payload)
    if status == 409:
        return "remote_conflict_no_retry"
    if status == 422:
        return "remote_rejected_no_retry"
    if status not in (200, 201):
        return "upload_failed"
    try:
        data = json.loads(response) if isinstance(response, (str, bytes)) else response
        returned_sha = data.get("content", {}).get("sha")
    except (ValueError, TypeError, AttributeError):
        return "accepted_requires_remote_confirmation"
    if returned_sha != new_sha:
        return "accepted_requires_remote_confirmation"
    return "accepted_requires_remote_confirmation"
