# -*- coding: utf-8 -*-
"""Distribución OAuth de Google Drive + OneDrive (MASTER -> GitHub -> CLIENT).

Solo develop puede publicar. No registra secretos ni contenido de rclone.conf.
Un cambio de token se comprueba antes de publicar o instalar.
Los montajes ya iniciados no se reinician aquí (requieren gestión aparte).
"""
import hashlib
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
from lib import rclone_two_mount_client_role as client_role
from lib import rclone_two_mount_rollout
from lib import rclone_utils

CONF_PATH = "/storage/.config/rclone/rclone.conf"
REMOTE_PATH = "rclone/rclone.conf.crypt"
MAX_CONF_BYTES = 1024 * 1024
# El worker ya despierta cada 60 s. El MASTER comprueba huella local cada
# minuto y contacta GitHub solo si cambió refresh_token/opciones o cada 6 h.
MASTER_INTERVAL = 60
MASTER_REMOTE_RECONCILE_INTERVAL = 6 * 60 * 60
MASTER_SETTLE_SECONDS = 10
MASTER_CORRUPT_CONFIRM_SECONDS = 60
MASTER_RECOVERY_RETRY_SECONDS = 5 * 60
MASTER_ONEDRIVE_HEALTH_INTERVAL = 15 * 60
MASTER_DRIVE_HEALTH_INTERVAL = 60 * 60
CLIENT_INTERVAL = 60 * 60

_lock = threading.Lock()
_last_tick = None  # Primer chequeo al arrancar, no al alcanzar X horas de uptime.
_last_master_confirmed_fp = None
_last_master_remote_checked_at = None
_last_master_onedrive_health_at = None
_last_master_drive_health_at = None
_master_corrupt_signature = None
_master_corrupt_since = None
_master_recovery_last_attempt = None


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



def _file_generation(path):
    """Identidad del fichero para detectar reemplazos incluso con bytes iguales.

    Esto NO es un bloqueo con rclone: solo detecta cambios ya completados.
    """
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return None
    if not os.path.isfile(path) or os.path.islink(path):
        raise ValueError("rclone.conf no es archivo regular seguro")
    return (info.st_dev, info.st_ino, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns)


def _config_mounts_active():
    """Fence conservador: procesos rclone mount usando este rclone.conf.

    Los procesos rclone NO respetan locks Python; nunca escribir su
    configuración compartida mientras alguno siga usando ese fichero.
    Se reconoce el --config de las unidades systemd de cloud/develop.
    Un mount rclone sin --config explícito se considera desconocido/busy.
    """
    target = os.path.realpath(CONF_PATH)
    try:
        entries = os.scandir("/proc")
    except OSError:
        return True  # No podemos demostrar que no haya otros escritores.
    try:
        for entry in entries:
            if not entry.name.isdigit() or int(entry.name) == os.getpid():
                continue
            try:
                with open(entry.path + "/cmdline", "rb") as stream:
                    args = [part.decode("utf-8", "replace")
                            for part in stream.read(16384).split(b"\x00") if part]
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError:
                # Si proc es parcialmente inaccesible, no demostrar inactividad.
                return True
            if not args or not os.path.basename(args[0]).startswith("rclone"):
                continue
            if "mount" not in args[1:10]:
                continue
            config = None
            for i, arg in enumerate(args[1:], 1):
                if arg == "--config" and i + 1 < len(args):
                    config = args[i + 1]
                    break
                if arg.startswith("--config="):
                    config = arg[len("--config="):]
                    break
            if config is None or os.path.realpath(config) == target:
                return True
        return False
    finally:
        entries.close()


def _install_generation_unchanged(path, expected, original):
    """Fence antes de os.replace: datos y generación deben coincidir."""
    if _config_mounts_active():
        return "mounts_active"
    if _file_generation(path) != expected:
        return "local_changed"
    try:
        current = _read_damaged_snapshot() if path == CONF_PATH else _read_stable(path)
    except (OSError, ValueError, RuntimeError):
        return "local_changed"
    if current != original:
        return "local_changed"
    return None


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
    stderr = proc.stderr[-8192:].lower()
    if policy.auth_failure(stderr):
        return "auth"
    if any(marker in stderr for marker in (
        b"rate limit", b"ratelimit", b"429", b"quota exceeded",
        b"throttl",
    )):
        return "rate_limited"
    return "unavailable"


def _legacy_sync_permitted():
    """No publicar ni recuperar rclone.conf legacy si el equipo usa 2 FUSE."""
    mode = rclone_two_mount_rollout.mode(
        getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
    )
    return mode in ("legacy", "prepared")


def _publish_master():
    if not _legacy_sync_permitted():
        return "two_mount_mode"
    if constants.CLOUD_BRANCH != "develop" or not device_utils.is_master_device():
        return "blocked"
    key = device_utils.get_key_from_authorized_keys()
    if not key:
        return "no_key"
    # Evitar capturar una escritura reciente de varios rclone mount.
    # Se reintentará en el próximo minuto sin publicar un fichero intermedio.
    local_stat = os.stat(CONF_PATH)
    if time.time() - local_stat.st_mtime < MASTER_SETTLE_SECONDS:
        return "local_settling"
    local = _read_stable(CONF_PATH)
    policy.validate_master_layout(local)  # Nunca subir un fichero truncado.
    remote = _remote_config(key)  # No publicar si no podemos verificar la base.
    policy.validate_master_layout(remote)
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
    # Otra rotación durante la subida debe publicarse en el ciclo siguiente.
    if _read_stable(CONF_PATH) != local:
        return "published_local_advanced"
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



def _read_damaged_snapshot():
    """Lectura acotada para conservar archivos dañados, sin seguir symlinks."""
    if os.path.islink(CONF_PATH):
        raise ValueError("No se admite enlace simbólico como configuración")
    if not os.path.exists(CONF_PATH):
        return None
    with open(CONF_PATH, "rb") as stream:
        data = stream.read(MAX_CONF_BYTES + 1)
    if len(data) > MAX_CONF_BYTES:
        raise ValueError("Configuración demasiado grande para recuperación")
    return data


def _master_probe_local(local, names):
    """Comprueba OAuth con copia privada: no renovar tokens del fichero real."""
    tmp = _write_candidate(CONF_PATH, local)
    try:
        result = {}
        for name in names:
            result[name] = _probe(name, tmp)
        return result
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _master_recover(mode, original=None, broken_names=()):
    """Recupera al MASTER desde la reserva MQC2, sin publicar ni reiniciar FUSE.

    mode=corrupt: restaura un snapshot completo validado.
    mode=auth: cambia solo tokens explícitamente fallidos y conserva opciones
    estáticas propias del MASTER. Ningún error de red/cuota provoca cambios.
    """
    if not _legacy_sync_permitted():
        return "two_mount_mode"
    if constants.CLOUD_BRANCH != "develop" or not device_utils.is_master_device():
        return "blocked"
    if mode not in ("corrupt", "auth"):
        raise ValueError("Modo de recuperación no admitido")
    key = device_utils.get_key_from_authorized_keys()
    if not key:
        return "no_key"

    # Si se produjo una renovación concurrente, no hacer nada destructivo.
    if _config_mounts_active():
        return "mounts_active"
    if _read_damaged_snapshot() != original:
        return "local_changed"
    initial_generation = _file_generation(CONF_PATH)
    if os.path.exists(CONF_PATH) and (
            time.time() - os.stat(CONF_PATH).st_mtime < MASTER_SETTLE_SECONDS):
        return "local_settling"

    published = _remote_config(key)
    names = policy.validate_master_layout(published)
    if mode == "corrupt":
        if original is not None and not policy.master_partial_identity_compatible(
                original, published):
            return "master_identity_mismatch"
        candidate = published
        verify_names = names
    else:
        if original is None:
            return "no_local"
        policy.validate_master_layout(original)
        try:
            # Ante AUTH explícito sí se acepta que haya cambiado únicamente
            # el access_token, siempre que el candidato remoto sea diferente.
            candidate = policy.tokens_from_master(
                original, published, broken_names, allow_same_refresh=True
            )
        except ValueError:
            return "no_new_token"
        verify_names = tuple(sorted(set(broken_names)))
        if not verify_names:
            return "no_failed_remote"

    # Restaurar solo si los remotos que vamos a reparar son accesibles.
    # En corrupción completa exigimos éxito de los CUATRO remotos.
    tmp = _write_candidate(CONF_PATH, candidate)
    try:
        provider = policy.sections(candidate)
        google_limited = 0
        for name in verify_names:
            result = _probe(name, tmp)
            if result == "ok":
                continue
            if (mode == "corrupt" and result == "rate_limited" and
                    provider[name].get("type", "").strip().lower() == "drive"):
                # Una cuota de Google Drive no bloquea rescatar las
                # bibliotecas OneDrive. Un error OAuth sí bloquea.
                google_limited += 1
                continue
            return "master_candidate_unverified"
        verified = _read_stable(tmp)
        policy.validate_master_layout(verified)
        if mode == "corrupt" and original is not None:
            if not policy.master_partial_identity_compatible(original, verified):
                return "master_identity_mismatch"
        state = _install_generation_unchanged(
            CONF_PATH, initial_generation, original
        )
        if state:
            return state
        if original == verified:
            return "unchanged"

        # Conservar una copia PRIVADA y con nombre exclusivo del fichero previo.
        # El respaldo también se crea si estaba corrupto; no sobrescribir otros.
        if original is not None:
            backup_tmp = _write_candidate(CONF_PATH, original)
            backup = (
                CONF_PATH + ".pre-master-recovery-" +
                time.strftime("%Y%m%d-%H%M%S", time.gmtime()) +
                "-" + os.path.basename(backup_tmp)
            )
            os.replace(backup_tmp, backup)

        # Segunda comprobación justo antes de cambiar el fichero activo.
        state = _install_generation_unchanged(
            CONF_PATH, initial_generation, original
        )
        if state:
            return state
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONF_PATH)
        tmp = None
        if google_limited:
            log_utils.write_log(
                "[rclone_sync] MASTER: bibliotecas verificadas; "
                "Google Drive limitado por cuota, comprobar más tarde",
                "WARNING",
            )
        return "master_recovered_restart_pending"
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)

def _recover_client():
    if not _legacy_sync_permitted():
        return "two_mount_mode"
    if device_utils.is_master_device():
        return "master"
    if not os.path.isfile(CONF_PATH):
        return "no_local"
    local = _read_stable(CONF_PATH)
    initial_generation = _file_generation(CONF_PATH)
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
            elif status in ("unavailable", "rate_limited"):
                unknown += 1
    finally:
        if os.path.exists(probe_file):
            os.unlink(probe_file)
    if not bad:
        return "unavailable" if unknown else "healthy"
    if _config_mounts_active():
        return "mounts_active"

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
        state = _install_generation_unchanged(
            CONF_PATH, initial_generation, local
        )
        if state:
            return state

        recovered = _read_stable(tmp)
        policy.oauth_tokens(recovered)
        backup = CONF_PATH + ".pre-recovery"
        backup_tmp = _write_candidate(CONF_PATH, local)
        try:
            os.replace(backup_tmp, backup)
        finally:
            if os.path.exists(backup_tmp):
                os.unlink(backup_tmp)

        state = _install_generation_unchanged(
            CONF_PATH, initial_generation, local
        )
        if state:
            return state
        os.chmod(tmp, 0o600)
        os.replace(tmp, CONF_PATH)
        tmp = None
        # Los procesos rclone mount pueden conservar su token en memoria.
        # NO reiniciar servicios aquí: podría interrumpir reproducción Kodi.
        return "recovered_restart_pending"
    finally:
        if tmp is not None and os.path.exists(tmp):
            os.unlink(tmp)


def _master_cycle(now):
    """Publicación + recuperación MASTER con prioridad a las bibliotecas."""
    if not _legacy_sync_permitted():
        return "two_mount_mode"
    global _last_master_confirmed_fp, _last_master_remote_checked_at
    global _last_master_onedrive_health_at, _last_master_drive_health_at
    global _master_corrupt_signature, _master_corrupt_since
    global _master_recovery_last_attempt

    try:
        local = _read_stable(CONF_PATH)
        policy.validate_master_layout(local)
    except (OSError, RuntimeError, ValueError, UnicodeError):
        # Confirmar dos observaciones estables: una escritura de rclone
        # a medias no debe provocar recuperación precipitada.
        try:
            raw = _read_damaged_snapshot()
        except (OSError, ValueError):
            return "master_corrupt_unsafe"
        signature = hashlib.sha256(
            raw if raw is not None else b"<missing-rclone-conf>"
        ).digest()
        if signature != _master_corrupt_signature:
            _master_corrupt_signature = signature
            _master_corrupt_since = now
            return "master_corrupt_pending"
        if now - _master_corrupt_since < MASTER_CORRUPT_CONFIRM_SECONDS:
            return "master_corrupt_pending"
        if (_master_recovery_last_attempt is not None and
                now - _master_recovery_last_attempt <
                MASTER_RECOVERY_RETRY_SECONDS):
            return "master_recovery_cooldown"
        _master_recovery_last_attempt = now
        return _master_recover("corrupt", original=raw)

    _master_corrupt_signature = None
    _master_corrupt_since = None

    # Sondar OneDrive (bibliotecas) cada 15 min, Drive cada 60 min.
    # No utilizar que FUSE esté montado como prueba de OAuth válido.
    sections = policy.sections(local)
    critical = sorted(name for name in policy.oauth_tokens(local)
                      if sections[name].get("type", "").lower() == "onedrive")
    secondary = sorted(name for name in policy.oauth_tokens(local)
                       if sections[name].get("type", "").lower() == "drive")
    inspect = []
    if (_last_master_onedrive_health_at is None or
            now - _last_master_onedrive_health_at >=
            MASTER_ONEDRIVE_HEALTH_INTERVAL):
        inspect += critical
        _last_master_onedrive_health_at = now
    if (_last_master_drive_health_at is None or
            now - _last_master_drive_health_at >=
            MASTER_DRIVE_HEALTH_INTERVAL):
        inspect += secondary
        _last_master_drive_health_at = now

    if inspect:
        states = _master_probe_local(local, inspect)
        broken = tuple(name for name in inspect if states.get(name) == "auth")
        if broken:
            if (_master_recovery_last_attempt is not None and
                    now - _master_recovery_last_attempt <
                    MASTER_RECOVERY_RETRY_SECONDS):
                return "master_recovery_cooldown"
            _master_recovery_last_attempt = now
            return _master_recover(
                "auth", original=local, broken_names=broken
            )
        # Cualquier fallo por cuota/red/permisos se trata como desconocido:
        # no se intenta restaurar ni modificar el archivo local.

    fp = policy.stable_oauth_fingerprint(local)
    if (fp == _last_master_confirmed_fp and
            _last_master_remote_checked_at is not None and
            now - _last_master_remote_checked_at <
            MASTER_REMOTE_RECONCILE_INTERVAL):
        return "healthy"

    status = _publish_master()
    if status in ("published", "unchanged"):
        _last_master_confirmed_fp = fp
        _last_master_remote_checked_at = now
    return status


_SAFE_V2_MASTER_RESULTS = {
    "created_verified", "updated_verified", "unchanged",
    "blocked_not_authorized", "blocked_master_not_ready",
    "blocked_missing_credentials", "blocked_missing_dependency",
    "blocked_repository_unverified", "blocked_remote_unavailable",
    "blocked_remote_invalid", "blocked_remote_static_change",
    "blocked_remote_identity", "blocked_local_health",
    "blocked_local_changed", "blocked_repository_changed",
    "conflict_no_retry", "put_failed", "put_unconfirmed",
    "blocked_readback_branch_drift", "blocked_readback_remote_invalid",
    "blocked_readback_mismatch", "published_local_changed_requires_recheck",
    "blocked_sync_failure", "blocked_master_runtime",
}


def _v2_master_tick():
    """Ruta MASTER v2, aislada del recuperador legacy y cerrada por flags.

    Se ejecutará solo en una futura release después de gates OAuth/Kodi.
    Nunca actúa como uploader de catalog ni reescribe la ruta legacy.
    """
    global _last_tick
    if (getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED", False)
            is not True or
            device_utils.get_device_role() != "MASTER" or
            constants.CLOUD_BRANCH != "develop"):
        return
    now = time.monotonic()
    if _last_tick is not None and now - _last_tick < MASTER_INTERVAL:
        return
    if not _lock.acquire(blocking=False):
        return
    try:
        _last_tick = now
        try:
            from lib import rclone_two_mount_master_runtime as v2_runtime
            status = v2_runtime.run_once(release_authorized=True)
        except Exception as exc:
            log_utils.write_log(
                "[rclone_sync_v2] Excepción (" + type(exc).__name__ + ")",
                "WARNING")
            return
        safe = status if status in _SAFE_V2_MASTER_RESULTS else "blocked_unknown_status"
        if safe in ("created_verified", "updated_verified"):
            log_utils.write_log("[rclone_sync_v2] " + safe, "INFO")
        elif safe != "unchanged":
            log_utils.write_log("[rclone_sync_v2] " + safe, "WARNING")
    finally:
        _lock.release()


def tick():
    """Cada 60s: legacy intacto; MASTER v2 con ruta independiente y flags."""

    global _last_tick, _last_master_confirmed_fp, _last_master_remote_checked_at
    global _last_master_onedrive_health_at, _last_master_drive_health_at
    if not getattr(constants, "RCLONE_TOKEN_SYNC_ENABLED", False):
        return
    if (getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is True and rclone_two_mount_rollout.mode(True) == "active"):
        # On the dev MASTER exercising CLIENT OAuth, never publish a
        # MASTER MQC2 v2 update in the same periodic iteration.
        if not getattr(constants,
                       "RCLONE_TWO_MOUNT_DEV_CLIENT_OAUTH_ON_MASTER", False):
            _v2_master_tick()
        # Independently gated CLIENT v2. The addon ships with this flag
        # False; no Kodi import or network traffic in the default build.
        if (getattr(constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED",
                    False) is True and
                client_role.allowed(device_utils.get_device_role())):
            try:
                import xbmc
                from lib import rclone_two_mount_client_worker as client_v2
                status = client_v2.tick(xbmc.executeJSONRPC,
                                        authorized=True)
                allowed = frozenset({
                    "BLOCKED_NOT_AUTHORIZED", "BLOCKED_RELEASE_GATES",
                    "BLOCKED_NOT_CLIENT", "BLOCKED_NOT_ACTIVE_OR_RECOVERY",
                    "DEFERRED_PLAYBACK", "DEFERRED_INTERVAL",
                    "BLOCKED_SOURCES", "BLOCKED_MEDIA",
                    "BLOCKED_GITHUB_AUTH", "HEALTHY_OR_UNAVAILABLE",
                    "BLOCKED_WORKER_ERROR", "BLOCKED_CANDIDATE",
                    "BLOCKED_PLAYBACK_OR_MEDIA", "BLOCKED_UNFINISHED_RECOVERY",
                    "BLOCKED_NOT_ROOT", "BLOCKED_OPERATIONS",
                    "BLOCKED_SNAPSHOT", "MANUAL_RECOVERY_REQUIRED",
                    "RECOVERED_VERIFIED", "ROLLED_BACK_VERIFIED",
                })
                if status not in allowed:
                    status = "BLOCKED_WORKER_ERROR"
                if status not in ("HEALTHY_OR_UNAVAILABLE",
                                  "DEFERRED_INTERVAL"):
                    log_utils.write_log("[rclone_sync_v2_client] " + status,
                                        "WARNING")
            except Exception:
                log_utils.write_log(
                    "[rclone_sync_v2_client] BLOCKED_WORKER_ERROR",
                    "WARNING")
        return
    if not _legacy_sync_permitted():
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
        _last_tick = now
        try:
            status = _master_cycle(now) if role == "MASTER" else _recover_client()
        except Exception as exc:
            log_utils.write_log(
                "[rclone_sync] Falló la comprobación ({})".format(type(exc).__name__),
                "WARNING",
            )
            return
        if status == "master_recovered_restart_pending":
            # Debe revalidar y conciliar nuevamente la siguiente ronda.
            _last_master_confirmed_fp = None
            _last_master_remote_checked_at = None
            _last_master_onedrive_health_at = None
            _last_master_drive_health_at = None
            log_utils.write_log(
                "[rclone_sync] MASTER: config recuperada desde reserva MQC2; "
                "montajes activos pueden requerir reinicio controlado",
                "WARNING",
            )
        elif status == "recovered_restart_pending":
            log_utils.write_log(
                "[rclone_sync] CLIENTE: token recuperado en disco; montajes "
                "activos pueden requerir reinicio controlado", "WARNING",
            )
        elif status == "published":
            log_utils.write_log("[rclone_sync] published", "INFO")
        elif status not in ("healthy", "unchanged", "local_settling",
                            "master_corrupt_pending", "master_recovery_cooldown"):
            log_utils.write_log("[rclone_sync] {}".format(status), "WARNING")
    finally:
        _lock.release()
