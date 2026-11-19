# -*- coding: utf-8 -*-
"""CLIENT v2: verificación de recuperación por cuenta, SIN instalación.

La ejecución requiere autorización explícita y callbacks. No crea conexiones
por sí sola; no escribe archivos, ni modifica unidades ni reinicia rclone.
El callback probe debe usar una copia temporal privada y limpiar sus bytes.
"""
from lib import rclone_two_mount_client_recovery as recovery
from lib import rclone_two_mount_config_routes as routes


def verify_once(*, account_index, auth_status, read_sources, head, get,
                probe, key, release_authorized=False, return_candidate=False):
    """Obtiene y verifica un candidato; nunca devuelve bytes en logs.

    read_sources(): (canonical, (account1, account2))
    head(): GitHub HEAD autenticado
    get(path): (status, contents) por la ruta v2 fija
    probe(index, candidate): devuelve 'ok' solo tras OAuth real de copia
    El resultado listo sigue exigiendo un aplicador transaccional posterior.
    """
    if release_authorized is not True:
        return "blocked_not_authorized"
    if auth_status != "auth":
        return "blocked_not_auth"
    if type(account_index) is not int or account_index not in (0, 1):
        return "blocked_account"
    if not key or not all(callable(x) for x in (
            read_sources, head, get, probe)):
        return "blocked_dependency"
    try:
        first = read_sources()
        if (not isinstance(first, tuple) or len(first) != 2 or
                not isinstance(first[1], (tuple, list)) or
                len(first[1]) != 2):
            return "blocked_local_sources"
        before = head()
        if not isinstance(before, str):
            return "blocked_head"
        status, response = get(routes.V2_REMOTE_PATH)
        observed = head()
        planned = recovery.prepare(
            account_index, first[0], first[1][account_index],
            status, response, key, auth_status=auth_status,
            release_authorized=True, repository_head=before,
            observed_head=observed)
        if planned["status"] != "candidate_requires_probe":
            return planned["status"]
        result = probe(account_index, planned["candidate_account"])
        # La sonda puede renovar su copia; nunca convertir ese cambio en
        # permiso para sobrescribir un writer rclone en ejecución.
        same_local = read_sources() == first
        same_remote = head() == before
        decision = recovery.confirm_probe(
            planned, result, baseline_unchanged=same_local,
            remote_head_unchanged=same_remote)
        if (return_candidate is True and
                decision == "probe_verified_requires_transactional_install"):
            return {"status": "candidate_probe_verified",
                    "prepared": planned}
        return decision
    except (OSError, ValueError, TypeError, KeyError, RuntimeError,
            UnicodeError, OverflowError):
        return "blocked_runtime_error"
