# -*- coding: utf-8 -*-
"""CLIENT v2: protocolo de recuperación reversible por cuenta, INACTIVO.

Adaptador de operaciones inyectadas. No conoce rutas reales, no ejecuta
systemctl, no crea archivos ni llama OAuth por sí solo. Los callbacks
operativos deberán disponer de journal durable, fsync y fencing de escritores.
"""
from lib import rclone_two_mount_client_recovery as recovery


def execute(prepared, *, authorized=False, verified_probe=False,
            playback_idle=False, operations=None):
    """Intenta aplicar un candidato comprobado con journal y rollback.

    Contrato obligatorio de operations:
      snapshot(i, expected) -> bool [respaldo durable, bloqueos y generaciones]
      stop(i) -> bool [detiene solo rclone de i, NO la otra cuenta]
      quiescent(i) -> bool [ningún escritor de i, ni montajes dependientes]
      still_current(i, expected) -> bool [bytes y generación exactos]
      install(i, candidate) -> bool [atomic 0600 + fsync + journal previo]
      start(i) -> bool [reinicio exclusivo de i]
      healthy(i) -> bool [FUSE + bind + medio comprobado]
      commit(i) -> bool [journal final durable]
      rollback(i) -> bool [restauración desde snapshot durable + reinicio]
      rollback_healthy(i) -> bool [cuenta original restaurada y legible]

    Si falla cualquier operación tras snapshot, intenta rollback.
    Si rollback no puede verificarse devuelve MANUAL_RECOVERY_REQUIRED.
    Nunca se afirma éxito si el commit durable falla.
    """
    if authorized is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if verified_probe is not True or playback_idle is not True:
        return "BLOCKED_UNVERIFIED_OR_PLAYBACK"
    if not isinstance(prepared, dict) or prepared.get("status") != (
            "candidate_requires_probe"):
        return "BLOCKED_CANDIDATE"
    i = prepared.get("account_index")
    old, new = prepared.get("baseline_account"), prepared.get("candidate_account")
    if (type(i) is not int or i not in (0, 1) or
            type(old) is not bytes or type(new) is not bytes or
            not old or not new or old == new):
        return "BLOCKED_CANDIDATE"
    names = ("snapshot", "stop", "quiescent", "still_current", "install",
             "start", "healthy", "commit", "rollback", "rollback_healthy")
    if operations is None or not all(
            callable(getattr(operations, name, None)) for name in names):
        return "BLOCKED_OPERATIONS"
    # Snapshot must be durable before making a single change. Its failure
    # must fail closed; never guess which artifacts were written.
    try:
        if operations.snapshot(i, old) is not True:
            return "BLOCKED_SNAPSHOT"
    except Exception:
        return "MANUAL_RECOVERY_REQUIRED"
    try:
        for action in (
                lambda: operations.stop(i),
                lambda: operations.quiescent(i),
                lambda: operations.still_current(i, old),
                lambda: operations.install(i, new),
                lambda: operations.start(i),
                lambda: operations.healthy(i),
                lambda: operations.commit(i)):
            if action() is not True:
                raise RuntimeError("transaction stage rejected")
        return "RECOVERED_VERIFIED"
    except Exception:
        try:
            if (operations.rollback(i) is True and
                    operations.rollback_healthy(i) is True):
                return "ROLLED_BACK_VERIFIED"
        except Exception:
            pass
        return "MANUAL_RECOVERY_REQUIRED"
