# -*- coding: utf-8 -*-
"""Reconciliación OAuth de dos montajes: POLÍTICA PURA, SIN EFECTOS.

MASTER: compara dos snapshots aislados crypt->OneDrive con el rclone.conf
canónico (2 OneDrive + 2 Drive). Produce un candidato que DEBE verificarse
con rclone antes de publicar MQC2. Nunca decide por expiry o mtime.

CLIENTE v2: construye un candidato desde el MASTER sólo para una cuenta
con fallo OAuth confirmado. NO lo instala mientras exista rclone mount.

No abre archivos, no consulta red, no escribe ni habilita la función.
"""
from lib import rclone_conf_merge as merge
from lib import rclone_mount_isolation as isolation
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_plan as plan

ACCOUNT_COUNT = 2


def _baseline(canonical, published):
    policy.validate_master_layout(canonical)
    policy.validate_master_layout(published)
    if not merge.same_non_token_settings(canonical, published):
        raise ValueError("Configuración canónica y MQC2 difieren en opciones")
    old = policy.oauth_tokens(canonical)
    remote = policy.oauth_tokens(published)
    if set(old) != set(remote):
        raise ValueError("Inventario OAuth canónico no coincide con MQC2")
    return old, remote


def _account(canonical, number, snapshot):
    """Valida cuenta aislada: exactamente crypt y su OneDrive, sin extras."""
    if type(number) is not int or number not in (0, 1):
        raise ValueError("Índice de cuenta no autorizado")
    canonical_part = plan.account_snapshot(canonical, number)
    if not merge.same_non_token_settings(canonical_part, snapshot):
        raise ValueError("Identidad o ajustes crypt/OneDrive diferentes")
    expected = policy.sections(canonical_part)
    incoming = policy.sections(snapshot)
    if set(incoming) != set(expected):
        raise ValueError("Faltan o sobran secciones en cuenta aislada")
    tokens = policy.oauth_tokens(snapshot)
    expected_tokens = policy.oauth_tokens(canonical_part)
    if set(tokens) != set(expected_tokens) or len(tokens) != 1:
        raise ValueError("Inventario OneDrive aislado incorrecto")
    name = next(iter(tokens))
    if incoming[name].get("type", "").strip().lower() != "onedrive":
        raise ValueError("La credencial no corresponde a OneDrive")
    if incoming[plan.ACCOUNT_REMOTES[number]].get(
            "type", "").strip().lower() != "crypt":
        raise ValueError("No se conserva la configuración crypt")
    return name, tokens[name]


def _account_sources(canonical, configs):
    if not isinstance(configs, (tuple, list)) or len(configs) != ACCOUNT_COUNT:
        raise ValueError("Se requieren dos snapshots de cuentas")
    found = {}
    for number, raw in enumerate(configs):
        name, token = _account(canonical, number, raw)
        if name in found:
            raise ValueError("Los dos montajes comparten una credencial OAuth")
        found[name] = (token, raw)
    return found


def prepare_master(canonical, account_configs, published):
    """Compone en memoria el candidato MASTER, SIN validar OAuth en la red.

    Si MQC2 cambió de refresh desde el snapshot canónico, no se puede
    determinar automáticamente cuál es más nuevo: bloquear y conciliar.
    Una salida `candidate_requires_probe` NUNCA autoriza publicar.
    """
    old, remote = _baseline(canonical, published)
    sources = _account_sources(canonical, account_configs)
    if any(old[name]["refresh_token"] != remote[name]["refresh_token"]
           for name in old):
        return {"status": "published_baseline_diverged",
                "candidate": None, "changed_names": ()}
    candidate = canonical
    changed = []
    for name, (token, isolated) in sorted(sources.items()):
        if old[name]["refresh_token"] == token["refresh_token"]:
            continue  # churn de access_token o expiry: no promocionar.
        candidate = policy.tokens_from_master(
            candidate, isolated, (name,)
        )
        changed.append(name)
    if not changed:
        return {"status": "unchanged", "candidate": None, "changed_names": ()}
    policy.validate_master_layout(candidate)
    if not merge.same_non_token_settings(candidate, canonical):
        raise ValueError("Los cambios alteraron las opciones estáticas")
    # Impedir incluso accidentalmente la alteración de Google Drive.
    canon_opts = policy.sections(canonical)
    new_opts = policy.sections(candidate)
    for name in canon_opts:
        if canon_opts[name].get("type", "").strip().lower() == "drive":
            if canon_opts[name] != new_opts[name]:
                raise ValueError("Google Drive no puede cambiar en candidato")
    if not policy.master_should_publish(candidate, published):
        raise ValueError("Candidato no tiene rotación OAuth verificable")
    return {"status": "candidate_requires_probe",
            "candidate": candidate, "changed_names": tuple(changed)}


def probe_gate(prepared, results):
    """Permite avanzar a REVALIDACIÓN, no autoriza publicar ni instalar.

    Solo `ok` explícito por cada cuenta rotada; cualquier otro estado
    (401, timeout, 429, permisos o error desconocido) bloquea.
    """
    if prepared.get("status") != "candidate_requires_probe":
        return "blocked"
    names = prepared.get("changed_names", ())
    if not names or not isinstance(results, dict):
        return "blocked"
    if any(results.get(name) != "ok" for name in names):
        return "probe_failed"
    return "revalidate_sources_before_publish"


def prepare_client(canonical_master, account_index, local_account,
                   confirmed_auth_error=False):
    """Candidato CLIENTE para una sola cuenta, sin alterar crypt ni instalar.

    Debe comprobarse una señal AUTH inequívoca antes de invocar con True.
    La prueba de conexión del candidato y la coordinación con rclone mount
    continúan siendo responsabilidad de una fase posterior.
    """
    if confirmed_auth_error is not True:
        return {"status": "no_explicit_oauth_error", "candidate": None}
    policy.validate_master_layout(canonical_master)
    name, ours = _account(
        canonical_master, account_index, local_account
    )
    target = plan.account_snapshot(canonical_master, account_index)
    from_master = policy.oauth_tokens(target)[name]
    if ours == from_master:
        return {"status": "no_alternative", "candidate": None}
    try:
        candidate = policy.tokens_from_master(
            local_account, target, (name,), allow_same_refresh=True
        )
    except ValueError:
        return {"status": "no_alternative", "candidate": None}
    if not merge.same_non_token_settings(candidate, local_account):
        raise ValueError("Intento de cambiar crypt en cliente")
    if set(policy.sections(candidate)) != set(policy.sections(local_account)):
        raise ValueError("Cambio de inventario aislado")
    return {"status": "candidate_requires_probe_and_safe_apply",
            "candidate": candidate, "remote": name}
