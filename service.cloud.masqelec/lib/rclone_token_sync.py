# -*- coding: utf-8 -*-
"""Distribución OAuth de Google Drive + OneDrive (MASTER -> GitHub -> CLIENT).

Solo develop puede publicar. No registra secretos ni contenido de rclone.conf.
Un cambio de token se comprueba antes de publicar o instalar.
Los montajes ya iniciados no se reinician aquí (requieren gestión aparte).
"""
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request

from lib import catalog_utils
from lib import chacha_pure
from lib import constants
from lib import device_utils
from lib import log_utils
from lib import rclone_token_policy as policy
from lib import rclone_utils

CONF_PATH = "/storage/.config/rclone/rclone.conf"
REMOTE_PATH = "rclone/rclone.conf.crypt"
MAX_CONF_BYTES = 1024 * 1024
# Revisión MASTER cada 30 min, pero no crear commits por cada rotación de OneDrive.
MASTER_INTERVAL = 30 * 60
MASTER_MIN_PUBLISH_GAP = 6 * 60 * 60
CLIENT_INTERVAL = 60 * 60

_lock = threading.Lock()
_last_tick = None  # Primer chequeo al arrancar, no al alcanzar X horas de uptime.
_last_published = None


def _read_stable(path):
    """Evita leer una escritura de rclone a medias."""
    if os.path.islink(path):
        raise ValueError("rclone.conf no puede ser un enlace simbólico")
    for _ in range(3):
        pre = os.stat(path)
        if pre.st_size <= 0 or pre.st_size > MAX_CONF_BYTES:
            raise ValueError("Tamaño de rclone.conf fuera de límites")
        with open(path, "rb") as stream:
            data = stream.read(MAX_CONF_BYTES + 1)
        post = os.stat(path)
        if (len(data) <= MAX_CONF_BYTES and pre.st_size == len(data)
                and pre.st_size == post.st_size and
                pre.st_mtime_ns == post.st_mtime_ns):
            return data
        time.sleep(0.2)
    raise RuntimeError("rclone.conf cambió durante la lectura")


def _remote_config(key):
    """Descarga en HTTPS y autentica MQC2 antes de utilizarlo."""
    url = (
        constants.CLOUD_RAW_BASE.rstrip("/") + "/" + REMOTE_PATH
        + "?sync=" + str(int(time.time()))
    )
    req = urllib.request.Request(url, headers={
        "User-Agent": "masQelec/1.0 (+Kodi)",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=25) as response:
        cipher = response.read(2 * MAX_CONF_BYTES + 1)
    if len(cipher) > 2 * MAX_CONF_BYTES:
        raise ValueError("Archivo MQC2 remoto demasiado grande")
    raw = chacha_pure.decrypt_v2(cipher, key)
    if not raw or len(raw) > MAX_CONF_BYTES:
        raise ValueError("Configuración remota inválida")
    policy.oauth_tokens(raw)
    return raw


def _probe(name, config_path):
    """Resultado: ok, auth, unavailable. No registra stderr (puede tener secretos)."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        return "unavailable"
    try:
        binary = rclone_utils.which_rclone()
        cmd = [
            binary, "lsf", name + ":", "--max-depth=1",
            "--config", config_path,
            "--retries=1", "--low-level-retries=1",
            "--contimeout=10s", "--timeout=20s",
        ]
        proc = subprocess.run(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            timeout=45, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"
    if proc.returncode == 0:
        return "ok"
    return "auth" if policy.auth_failure(proc.stderr[-8192:]) else "unavailable"


def _publish_master():
    if constants.CLOUD_BRANCH != "develop" or not device_utils.is_master_device():
        return "blocked"
    key = device_utils.get_key_from_authorized_keys()
    if not key:
        return "no_key"
    local = _read_stable(CONF_PATH)
    remote = _remote_config(key)  # No publicar si no podemos verificar la base.
    if not policy.master_should_publish(local, remote):
        return "unchanged"
    changed = policy.changed_refresh_names(local, remote)

    # El refresh_token cambia con frecuencia en OneDrive. No basta comparar
    # fechas de access_token; probar cada credencial distinta en una COPIA.
    temp_conf = None
    fd, temp_conf = tempfile.mkstemp(
        prefix=".rclone-verify-", suffix=".conf", dir="/tmp"
    )
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(local)
            stream.flush()
            os.fsync(stream.fileno())
        for name in changed:
            if _probe(name, temp_conf) != "ok":
                return "candidate_unverified"
    finally:
        if temp_conf is not None and os.path.exists(temp_conf):
            os.unlink(temp_conf)

    # No publicar si rclone ha renovado la configuración mientras probábamos.
    if _read_stable(CONF_PATH) != local:
        return "local_changed"

    token = catalog_utils._gh_get_plain_token()
    if not token:
        return "no_github_token"
    encrypted = chacha_pure.encrypt_v2(local, key).encode("ascii") + b"\n"
    fd, temp = tempfile.mkstemp(prefix=".rclone-publish-", suffix=".crypt", dir="/tmp")
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encrypted)
            stream.flush()
            os.fsync(stream.fileno())
        if not catalog_utils._upload_file(token, temp, REMOTE_PATH):
            return "upload_failed"
    finally:
        if os.path.isfile(temp):
            os.unlink(temp)
    return "published"


def _write_candidate(path, data):
    fd, tmp = tempfile.mkstemp(prefix=".rclone-recovery-", dir=os.path.dirname(path))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        return tmp
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _recover_client():
    if device_utils.is_master_device():
        return "master"
    if not os.path.isfile(CONF_PATH):
        return "no_local"
    local = _read_stable(CONF_PATH)
    names = sorted(policy.oauth_tokens(local))
    if not names:
        return "no_oauth"

    # Probar una copia: una renovación durante el sondeo no debe sobrescribir
    # el rclone.conf que están usando los cuatro montajes.
    probe_file = _write_candidate(CONF_PATH, local)
    try:
        bad = []
        unknown = 0
        for name in names:
            status = _probe(name, probe_file)
            if status == "auth":
                bad.append(name)
            elif status == "unavailable":
                unknown += 1
    finally:
        if os.path.exists(probe_file):
            os.unlink(probe_file)
    if not bad:
        return "unavailable" if unknown else "healthy"

    key = device_utils.get_key_from_authorized_keys()
    if not key:
        return "no_key"
    remote = _remote_config(key)
    try:
        candidate = policy.tokens_from_master(local, remote, bad)
    except ValueError:
        return "no_new_token"

    # La prueba con --config temporal puede renovar el access_token sin
    # modificar la configuración activa del cliente.
    tmp = _write_candidate(CONF_PATH, candidate)
    try:
        for name in bad:
            if _probe(name, tmp) != "ok":
                return "candidate_failed"

        # No sobreescribir una renovación concurrente de rclone.
        if _read_stable(CONF_PATH) != local:
            return "local_changed"

        recovered = _read_stable(tmp)
        policy.oauth_tokens(recovered)
        backup = CONF_PATH + ".pre-recovery"
        backup_tmp = _write_candidate(CONF_PATH, local)
        try:
            os.replace(backup_tmp, backup)
        finally:
            if os.path.exists(backup_tmp):
                os.unlink(backup_tmp)

        os.chmod(tmp, 0o600)
        os.replace(tmp, CONF_PATH)
        tmp = None
        # Los procesos rclone mount pueden conservar su token en memoria.
        # NO reiniciar servicios aquí: podría interrumpir reproducción Kodi.
        return "recovered_restart_pending"
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)


def tick():
    """Invocado cada 60s por el servicio, trabajo real cada 30/60 min."""
    global _last_tick, _last_published
    if not getattr(constants, "RCLONE_TOKEN_SYNC_ENABLED", False):
        return
    if constants.CLOUD_BRANCH != "develop":
        return
    role = device_utils.get_device_role()
    interval = MASTER_INTERVAL if role == "MASTER" else CLIENT_INTERVAL
    now = time.monotonic()
    if _last_tick is not None and now - _last_tick < interval:
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        # Sin revalidar credenciales recientemente publicadas: OneDrive suele
        # cambiar refresh_token con cada renovación y generaría commits continuos.
        if (role == "MASTER" and _last_published is not None and
                now - _last_published < MASTER_MIN_PUBLISH_GAP):
            return
        # Si falla la red, reintentar en el siguiente intervalo, no cada 60 s.
        _last_tick = time.monotonic()
        try:
            status = _publish_master() if role == "MASTER" else _recover_client()
        except Exception as exc:
            log_utils.write_log(
                "[rclone_sync] Falló la comprobación ({})".format(type(exc).__name__),
                "WARNING",
            )
            return
        if status == "published":
            _last_published = time.monotonic()
            log_utils.write_log("[rclone_sync] published", "INFO")
        elif status == "recovered_restart_pending":
            log_utils.write_log(
                "[rclone_sync] token recuperado en disco; montajes en ejecución "
                "pueden requerir reinicio controlado", "WARNING"
            )
        elif status not in ("healthy", "unchanged"):
            log_utils.write_log("[rclone_sync] {}".format(status), "WARNING")
    finally:
        _lock.release()
