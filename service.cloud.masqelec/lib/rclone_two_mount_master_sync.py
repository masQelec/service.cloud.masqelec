# -*- coding: utf-8 -*-
"""MASTER v2: reconciliación MQC2 y create/update CAS por callbacks explícitos.

Sin side effects por sí solo, no lo importa service.py. No hay GET/PUT
implícitos: read_sources, health_gate y transporte deben ser inyectados.
Solo la ruta rclone/rclone-v2.conf.crypt puede ser escrita; nunca legacy.
"""
import base64
import hmac
import json
import re

from lib import rclone_conf_merge as merge
from lib import cloud_version_routes as cloud_routes
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_oauth as oauth
from lib import rclone_two_mount_publish_guard as crypt
from lib import rclone_two_mount_config_routes as routes

SHA = re.compile(r"[a-f0-9]{40}\Z")
MAX_RESPONSE = 4 * crypt.MAX_ENCRYPTED_BYTES


def compose_current(canonical, accounts):
    """MASTER local: crypt/OneDrive de cuentas aisladas; Drive de canónico.

    Extrae solo tokens OneDrive de account1 y account2; nunca promociona
    opciones estáticas, contraseñas crypt o identidades de cuenta diferentes.
    """
    if type(canonical) is not bytes or len(canonical) > 1024 * 1024:
        raise ValueError("Invalid canonical snapshot")
    policy.validate_master_layout(canonical)
    sources = oauth._account_sources(canonical, accounts)
    candidate = canonical
    for name, (token, source) in sorted(sources.items()):
        if policy.oauth_tokens(candidate)[name] != token:
            candidate = policy.tokens_from_master(
                candidate, source, (name,), allow_same_refresh=True)
    policy.validate_master_layout(candidate)
    if not merge.same_non_token_settings(candidate, canonical):
        raise ValueError("Static options changed")
    before = policy.sections(canonical)
    after = policy.sections(candidate)
    for name, options in before.items():
        if options.get("type", "").strip().lower() == "drive":
            if options != after[name]:
                raise ValueError("Google Drive changed during compose")
    return candidate


def _remote_contents(status, body, key):
    if type(status) is not int:
        return ("blocked_remote_unavailable", None, None)
    if status == 404:
        # Solo el GET autenticado al repositorio cuyo HEAD fue verificado.
        return ("missing", None, None)
    if status != 200:
        return ("blocked_remote_unavailable", None, None)
    try:
        if isinstance(body, (str, bytes)) and len(body) > MAX_RESPONSE:
            return ("blocked_remote_invalid", None, None)
        data = crypt.decode_remote_contents(body, key)
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return ("blocked_remote_invalid", None, None)
    return ("present", data["sha"], data["canonical"])


def prepare(canonical, accounts, remote_status, remote_body, key,
            *, repository_verified=False):
    """Decide si falta archivo, cambió refresh, o no se debe actualizar.

    No basta mtime, access_token, expiry ni que GH haya devuelto 404.
    Un remoto existente con opciones distintas se bloquea sin sobrescribir.
    """
    if repository_verified is not True:
        return {"status": "blocked_repository_unverified"}
    candidate = compose_current(canonical, accounts)
    result, sha, remote = _remote_contents(remote_status, remote_body, key)
    if result.startswith("blocked"):
        return {"status": result}
    current = policy.oauth_tokens(candidate)
    if result == "missing":
        return {"status": "create_requires_health",
                "canonical": candidate, "sha": None,
                "names": tuple(sorted(current))}
    if not merge.same_non_token_settings(candidate, remote):
        return {"status": "blocked_remote_static_change"}
    remote_tokens = policy.oauth_tokens(remote)
    if set(current) != set(remote_tokens):
        return {"status": "blocked_remote_identity"}
    changed = tuple(sorted(
        name for name in current
        if current[name]["refresh_token"] !=
        remote_tokens[name]["refresh_token"]))
    if not changed:
        return {"status": "unchanged"}
    return {"status": "update_requires_health", "canonical": candidate,
            "sha": sha, "names": changed}


def _parse_put(status, response, expected_blob, creating):
    if status in (409, 422):
        return ("conflict_no_retry", None)
    if status != (201 if creating else 200):
        return ("put_failed", None)
    try:
        if isinstance(response, (str, bytes)) and len(response) > 65536:
            return ("put_unconfirmed", None)
        data = json.loads(response) if isinstance(
            response, (str, bytes)) else response
        actual = data["content"]["sha"]
        revision = data["commit"]["sha"]
        if (not isinstance(actual, str) or
                not hmac.compare_digest(actual, expected_blob) or
                not isinstance(revision, str) or not SHA.fullmatch(revision)):
            return ("put_unconfirmed", None)
    except (ValueError, TypeError, KeyError, AttributeError):
        return ("put_unconfirmed", None)
    return ("accepted_requires_readback", revision)


def sync_once(read_sources, head, get, put, health_gate, key, token, *,
              release_authorized=False, master_attested=False,
              branch):
    """Master-v2 workflow inyectado. No crea sockets por sí solo.

    head(): SHA autenticado de la rama seleccionada.
    get(path): (status, contents_body) autenticado GitHub.
    put(path, payload): (status, response_body), sin reintentos.
    health_gate(candidate, names): {remote: 'ok'} por fuente REAL comprobada.
    read_sources(): (canonical, (account1, account2)) del almacenamiento local.

    Los bools son barreras necesarias, no pruebas suficientes. El caller
    debe asegurar rol MASTER y no exponer claves/tokens en logs.
    """
    if release_authorized is not True or master_attested is not True:
        return "blocked_not_authorized"
    if not cloud_routes.rclone_transport_branch_allowed(branch):
        return "blocked_not_authorized"
    if (not all(callable(x) for x in (
            read_sources, head, get, put, health_gate)) or
            not isinstance(key, (bytes, str)) or not key or
            not isinstance(token, str) or not token):
        return "blocked_missing_dependency"
    try:
        before_head = head()
        if not isinstance(before_head, str) or not SHA.fullmatch(before_head):
            return "blocked_repository_unverified"
        before = read_sources()
        if (not isinstance(before, tuple) or len(before) != 2 or
                not isinstance(before[1], (tuple, list)) or
                len(before[1]) != 2):
            return "blocked_local_sources"
        status, body = get(routes.V2_REMOTE_PATH)
        plan = prepare(before[0], before[1], status, body, key,
                       repository_verified=True)
        operation = plan["status"]
        if operation == "unchanged":
            return "unchanged"
        if operation not in ("create_requires_health",
                             "update_requires_health"):
            return operation
        states = health_gate(plan["canonical"], plan["names"])
        if not isinstance(states, dict) or any(
                states.get(name) != "ok" for name in plan["names"]):
            return "blocked_local_health"
        # Una renovación del refresh local durante una prueba impide enviar
        # un snapshot ya viejo. No es un lock sobre procesos rclone.
        if read_sources() != before:
            return "blocked_local_changed"
        if head() != before_head:
            return "blocked_repository_changed"
        payload_bytes = crypt.encode_candidate(plan["canonical"], key)
        expected_blob = crypt.git_blob_sha(payload_bytes)
        payload = {
            "message": "Verified master v2 MQC2 snapshot",
            "branch": branch,
            "content": base64.b64encode(payload_bytes).decode("ascii"),
        }
        creating = operation == "create_requires_health"
        if not creating:
            payload["sha"] = plan["sha"]
        write_status, write_body = put(routes.V2_REMOTE_PATH, payload)
        result, commit = _parse_put(
            write_status, write_body, expected_blob, creating)
        if result != "accepted_requires_readback":
            return result
        if head() != commit:
            return "blocked_readback_branch_drift"
        final_status, final_body = get(routes.V2_REMOTE_PATH)
        final_type, final_sha, final_canonical = _remote_contents(
            final_status, final_body, key)
        if final_type != "present":
            return "blocked_readback_remote_invalid"
        if (not hmac.compare_digest(final_sha, expected_blob) or
                not hmac.compare_digest(final_canonical, plan["canonical"])):
            return "blocked_readback_mismatch"
        if head() != commit:
            return "blocked_readback_branch_drift"
        if read_sources() != before:
            # PUT ya ocurrió; no declarar éxito, re-evaluar otra ronda.
            return "published_local_changed_requires_recheck"
        return "created_verified" if creating else "updated_verified"
    except (OSError, ValueError, TypeError, KeyError, RuntimeError,
            UnicodeError, OverflowError):
        return "blocked_sync_failure"
