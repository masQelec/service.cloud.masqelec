# -*- coding: utf-8 -*-
"""Drop-ins systemd para rollback OAuth sin sobrescribir rclone.conf.

Generador PURO. Los cuatro servicios legacy siguen existiendo; solo se
sustituye el --config de ExecStart por una copia privada de recuperación.
No toca binarios, remotos, rutas Kodi, Google Drive ni ficheros del host.
"""
import os
import shlex

from lib import rclone_mount_isolation as isolation
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout

DROPIN = "90-masqelec-oauth-recovery.conf"


def overrides(legacy_units, recovery_conf):
    """Devuelve cuatro ficheros (unit_name, bytes) sin secretos.

    recovery_conf ha de ser un fichero privado ya creado por el journal;
    no se aceptan rutas relativas ni caracteres de control.
    """
    plan.validate_legacy_units(legacy_units)
    if (not isinstance(recovery_conf, str) or
            not os.path.isabs(recovery_conf) or
            os.path.normpath(recovery_conf) != recovery_conf or
            any(ord(c) < 33 or ord(c) > 126 for c in recovery_conf) or
            not recovery_conf.endswith(
                "/canonical-recovery-candidate.conf")):
        raise ValueError("Invalid private recovery path")
    out = {}
    for unit in rollout.LEGACY_SERVICES:
        args = isolation._start_args(legacy_units[unit])
        if isolation._config_arg(args) != isolation.LIVE_CONFIG:
            raise ValueError("Legacy config source changed")
        if "--config" in args:
            pos = args.index("--config")
            args[pos + 1] = recovery_conf
        else:
            candidates = [
                i for i, arg in enumerate(args)
                if arg.startswith("--config=")]
            if len(candidates) != 1:
                raise ValueError("Unsupported config option")
            args[candidates[0]] = "--config=" + recovery_conf
        if isolation._config_arg(args) != recovery_conf:
            raise ValueError("Incomplete override")
        # Nunca interpolar shell ni añadir tokens a los servicios.
        cmd = " ".join(shlex.quote(value) for value in args)
        out[unit] = (
            "[Service]\n"
            "ExecStart=\n"
            "ExecStart=" + cmd + "\n"
        ).encode("utf-8")
    if set(out) != set(rollout.LEGACY_SERVICES):
        raise ValueError("Incomplete legacy override set")
    return out
