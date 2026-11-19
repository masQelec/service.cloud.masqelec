# -*- coding: utf-8 -*-
"""CLIENT v2: preparar recuperación OAuth por cuenta; sin escritura ni red.

Este módulo NO modifica account*.conf, no reinicia servicios y no llama
GitHub. Los callbacks de transporte/sondeo pertenecerán a un adaptador
operativo futuro, autorizado por separado. No registrar bytes OAuth.
"""
import hmac
import re

from lib import rclone_token_policy as policy
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_publish_guard as mqc2
from lib import rclone_two_mount_config_routes as routes

_SHA = re.compile(r"[a-f0-9]{40}\Z")


def prepare(account_index, local_canonical, local_account,
            remote_http_status, remote_contents, key, *, auth_status,
            release_authorized=False, repository_head=None,
            observed_head=None):
    """Resultado con estado; solo 'candidate_requires_probe' contiene bytes.

    Debe llamarse después de observar AUTH real de la cuenta; la respuesta
    no autoriza instalación ni confirma que el candidato OAuth sea válido.
    Los dos HEAD deben proceder de lecturas autenticadas independientes.
    """
    if release_authorized is not True:
        return {"status": "blocked_not_authorized"}
    if auth_status != "auth":
        return {"status": "blocked_not_auth"}
    if type(account_index) is not int or account_index not in (0, 1):
        return {"status": "blocked_account"}
    if (not isinstance(repository_head, str) or
            not _SHA.fullmatch(repository_head) or
            not isinstance(observed_head, str) or
            not hmac.compare_digest(repository_head, observed_head)):
        return {"status": "blocked_repository_changed"}
    if remote_http_status != 200:
        return {"status": "blocked_remote_unavailable"}
    if (not isinstance(local_canonical, bytes) or
            not isinstance(local_account, bytes)):
        return {"status": "blocked_local_invalid"}
    try:
        policy.validate_master_layout(local_canonical)
        expected_account = plan.account_snapshot(local_canonical, account_index)
        # El account real puede haber renovado OAuth desde el canónico.
        # La identidad y las opciones, excepto token, deben seguir iguales.
        from lib import rclone_conf_merge as conf
        if not conf.same_non_token_settings(local_account, expected_account):
            return {"status": "blocked_local_identity"}
        account_sections = policy.sections(local_account)
        account_tokens = policy.oauth_tokens(local_account)
        if len(account_tokens) != 1:
            return {"status": "blocked_local_identity"}
        name = next(iter(account_tokens))
        if account_sections[name].get("type", "").lower() != "onedrive":
            return {"status": "blocked_local_identity"}
        if not key:
            return {"status": "blocked_key"}
        decoded = mqc2.decode_remote_contents(remote_contents, key)
        remote = decoded["canonical"]
        # Conservar toda la configuración canónica local excepto token OAuth.
        # Esto valida la identidad de secciones y remotos, incluso Drive/crypt.
        candidate_canonical = policy.tokens_from_master(
            local_canonical, remote, (name,), allow_same_refresh=True)
        candidate_account = plan.account_snapshot(
            candidate_canonical, account_index)
        if not conf.same_non_token_settings(local_account, candidate_account):
            return {"status": "blocked_account_identity"}
        if candidate_account == local_account:
            return {"status": "blocked_no_alternative_token"}
        # El fichero remoto debe ser el endpoint v2, sin fallback legacy.
        if routes.remote_path_for_mount_mode("active") != routes.V2_REMOTE_PATH:
            return {"status": "blocked_route"}
        return {
            "status": "candidate_requires_probe",
            "account_index": account_index,
            "remote_sha": decoded["sha"],
            "candidate_account": candidate_account,
            "baseline_account": local_account,
        }
    except (ValueError, TypeError, KeyError, UnicodeError, OverflowError):
        return {"status": "blocked_invalid_or_incompatible"}


def confirm_probe(prepared, probe_status, *, baseline_unchanged=False,
                  remote_head_unchanged=False):
    """Solo devuelve una aprobación LÓGICA, nunca aplica los bytes.

    El adaptador futuro deberá hacer rollback durable y revalidar de nuevo
    bajo bloqueo exclusivo antes de cualquier escritura/restart.
    """
    if not isinstance(prepared, dict) or prepared.get("status") != (
            "candidate_requires_probe"):
        return "blocked_no_candidate"
    if (probe_status != "ok" or baseline_unchanged is not True or
            remote_head_unchanged is not True):
        return "blocked_probe_or_generation"
    return "probe_verified_requires_transactional_install"
