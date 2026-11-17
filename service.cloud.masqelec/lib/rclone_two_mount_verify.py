# -*- coding: utf-8 -*-
"""Sondeo REAL de OneDrive en copia PRIVADA, sin tocar montajes activos.

El comando rclone lsf es de solo lectura en remoto, pero puede RENOVAR
OAuth en su fichero temporal. Se captura esa renovación para una fase
posterior; jamás se escribe rclone.conf ni se publica en GitHub aquí.
"""
import os
import re
import subprocess
import tempfile

from lib import rclone_two_mount_oauth as coordination
from lib import rclone_token_policy as policy

MAX_CONFIG = 1024 * 1024


def probe_one(canonical, index, source, rclone_binary, runner=subprocess.run):
    """Resultado {status, post_probe, refresh_rotated}, sin logs de secretos.

    status: ok/auth/rate_limited/unavailable/tampered.
    Solo 'ok' permite pasar a revalidación de las fuentes reales.
    """
    name, before_token = coordination._account(canonical, index, source)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Nombre remoto OAuth no seguro")
    if not isinstance(source, bytes) or not 0 < len(source) <= MAX_CONFIG:
        raise ValueError("Configuración aislada inválida")
    if not isinstance(rclone_binary, str) or not rclone_binary.startswith("/"):
        raise ValueError("Ruta ejecutable no absoluta")

    with tempfile.TemporaryDirectory(
            prefix="masqelec-v2-oauth-probe-", dir="/tmp") as directory:
        os.chmod(directory, 0o700)
        path = os.path.join(directory, "probe.conf")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(source)
                stream.flush()
                os.fsync(stream.fileno())
        except BaseException:
            try:
                os.close(fd)
            except OSError:
                pass
            raise

        cmd = [
            rclone_binary, "lsf", name + ":",
            "--config", path, "--max-depth=1",
            "--retries=1", "--low-level-retries=1",
            "--contimeout=10s", "--timeout=20s",
        ]
        try:
            result = runner(
                cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                timeout=45, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return {"status": "unavailable", "post_probe": None,
                    "refresh_rotated": False}

        if getattr(result, "returncode", 1) != 0:
            err = (getattr(result, "stderr", b"") or b"")[-8192:]
            if policy.auth_failure(err):
                state = "auth"
            elif any(word in err.lower() for word in (
                    b"rate limit", b"429", b"quota exceeded", b"throttl")):
                state = "rate_limited"
            else:
                state = "unavailable"
            return {"status": state, "post_probe": None,
                    "refresh_rotated": False}
        try:
            info = os.lstat(path)
            if not os.path.isfile(path) or os.path.islink(path):
                raise ValueError("Sondeo escribió enlace inválido")
            if info.st_size <= 0 or info.st_size > MAX_CONFIG:
                raise ValueError("Configuración de sondeo fuera de límites")
            with open(path, "rb") as fd:
                after = fd.read(MAX_CONFIG + 1)
            if len(after) != info.st_size:
                raise ValueError("Sondeo escribió configuración inestable")
            _, updated = coordination._account(canonical, index, after)
            if not isinstance(updated.get("refresh_token"), str):
                raise ValueError("Token sondeado inválido")
        except (OSError, ValueError, UnicodeError, TypeError):
            return {"status": "tampered", "post_probe": None,
                    "refresh_rotated": False}
        return {
            "status": "ok",
            "post_probe": after,
            "refresh_rotated":
                before_token["refresh_token"] != updated["refresh_token"],
        }
