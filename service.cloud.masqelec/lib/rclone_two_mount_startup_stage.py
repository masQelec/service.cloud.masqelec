# -*- coding: utf-8 -*-
"""Staging local de 2 FUSE + 4 bind, solo tras actualizar el addon.

No network / OAuth / systemctl / mount / GitHub / Kodi; NO instala unidades.
Escribe SOLO en un directorio privado de preparación en /storage.
Jamás modifica rclone.conf, system.d, los 4 montajes ni sus rutas .strm.
Por defecto, RCLONE_TWO_MOUNT_STAGING_ENABLED=False bloquea TODO IO.
"""
import json
import os
import shutil
import stat
import tempfile

from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout

LOCAL_CONF = "/storage/.config/rclone/rclone.conf"
LEGACY_UNIT_DIR = "/storage/.config/system.d"
STAGING_PARENT = "/storage/.config/masqelec/rclone-v2-staging"
_MAX_SOURCE = 1024 * 1024


def _generation(s):
    return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)


def _read_file(path, *, confidential=False):
    """No seguir symlink de último componente; detectar lectura concurrente."""
    original = os.lstat(path)
    if not stat.S_ISREG(original.st_mode):
        raise ValueError("Fuente no es archivo regular")
    if confidential and stat.S_IMODE(original.st_mode) & 0o077:
        raise ValueError("Permisos OAuth inseguros")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or
                not 0 < before.st_size <= _MAX_SOURCE or
                _generation(before) != _generation(original)):
            raise ValueError("Fuente cambió o tamaño inválido")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            content = stream.read(_MAX_SOURCE + 1)
        after = os.fstat(fd)
    finally:
        os.close(fd)
    latest = os.lstat(path)
    if (len(content) != before.st_size or
            _generation(before) != _generation(after) or
            _generation(before) != _generation(latest)):
        raise ValueError("Fuente cambió durante la lectura")
    return content, _generation(latest)


def _read_sources(conf_path, unit_dir):
    canonical = _read_file(conf_path, confidential=True)
    units = {}
    generations = {}
    for name in rollout.LEGACY_SERVICES:
        raw, generation = _read_file(os.path.join(unit_dir, name))
        units[name] = raw
        generations[name] = generation
    return canonical, units, generations


def _private_directory(path):
    s = os.lstat(path)
    if (not stat.S_ISDIR(s.st_mode) or
            stat.S_IMODE(s.st_mode) != 0o700 or
            s.st_uid != os.geteuid()):
        raise ValueError("Directorio privado inválido")


def _expected_artifacts(canonical, units):
    """Solo snapshots de token LOCAL, no refresh remoto ni exploración."""
    artifacts = plan.generate(canonical, units)
    public = plan.public_manifest(artifacts)
    # Este staging NO ha autenticado MQC2; no etiquetarlo como verified.
    public["credential_source"] = "existing_local_config_unverified"
    public["activation"] = "stage_only"
    public["live_install_allowed"] = False
    manifest = (json.dumps(public, sort_keys=True, indent=2) + "\n").encode(
        "utf-8")
    expected = dict(artifacts)
    expected["rollout-manifest.json"] = (manifest, 0o600)
    if len(expected) != 9:
        raise ValueError("Inventario de artefactos inválido")
    if any(os.path.basename(name) != name or "/" in name
           for name in expected):
        raise ValueError("Nombre de artefacto no seguro")
    return expected


def _existing_matches(folder, expected):
    """Solo aceptar directorio cerrado con exactamente 9 artefactos."""
    try:
        _private_directory(folder)
        if set(os.listdir(folder)) != set(expected):
            return False
        for name, (content, mode) in expected.items():
            path = os.path.join(folder, name)
            info = os.lstat(path)
            if (not stat.S_ISREG(info.st_mode) or
                    info.st_uid != os.geteuid() or
                    stat.S_IMODE(info.st_mode) != mode):
                return False
            if _read_file(path)[0] != content:
                return False
        return True
    except (OSError, ValueError):
        return False


def _write_artifact(folder, name, content, mode):
    flags = (os.O_WRONLY | os.O_CREAT | os.O_EXCL |
             getattr(os, "O_NOFOLLOW", 0))
    fd = os.open(os.path.join(folder, name), flags, 0o600)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
        os.fsync(fd)
    finally:
        os.close(fd)


def _sync_dir(path):
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    fd = os.open(path, flags)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def stage_on_startup(*, staging_enabled=False, conf_path=LOCAL_CONF,
                     unit_dir=LEGACY_UNIT_DIR, parent=STAGING_PARENT,
                     state_path=rollout.STATE_PATH):
    """Preparar sin instalar. Devuelve solo estados; sin logs ni excepciones.

    La bandera de staging NO es la bandera de activación de FUSE.
    Mientras ambos False, el servicio permanece sin cambios.
    """
    if staging_enabled is not True:
        return "disabled"
    mode = rollout.mode(False, state_path=state_path)
    if mode == "unsafe":
        return "blocked_unsafe_mode"
    if mode == "active":
        return "blocked_active_mode"
    try:
        first = _read_sources(conf_path, unit_dir)
    except (OSError, ValueError, UnicodeError):
        return "blocked_local_sources"
    try:
        expected = _expected_artifacts(first[0][0], first[1])
    except (ValueError, TypeError, UnicodeError):
        return "blocked_layout"
    # Antes de crear archivos, verificar que ni rclone ni el actualizador
    # legacy reescribieron las fuentes mientras se generaba el candidato.
    try:
        if _read_sources(conf_path, unit_dir) != first:
            return "blocked_source_changed"
    except (OSError, ValueError):
        return "blocked_source_changed"
    try:
        os.makedirs(parent, mode=0o700, exist_ok=True)
        _private_directory(parent)
    except (OSError, ValueError):
        return "blocked_private_parent"

    target = os.path.join(parent, rollout.CANDIDATE_ID)
    if os.path.lexists(target):
        return ("already_staged" if _existing_matches(target, expected)
                else "blocked_stale_or_unsafe_stage")

    temp = None
    try:
        temp = tempfile.mkdtemp(prefix=".candidate-", dir=parent)
        _private_directory(temp)
        for name, (content, file_mode) in expected.items():
            _write_artifact(temp, name, content, file_mode)
        _sync_dir(temp)
        if not _existing_matches(temp, expected):
            return "blocked_stage_validation"
        if _read_sources(conf_path, unit_dir) != first:
            return "blocked_source_changed"
        if os.path.lexists(target):
            return "blocked_concurrent_stage"
        # Parent 0700 y privilegio de mismo UID: no sustituir staged antiguo.
        os.rename(temp, target)
        temp = None
        _sync_dir(parent)
        return "staged_private_local"
    except (OSError, ValueError):
        return "blocked_stage_write_or_source_changed"
    finally:
        if temp is not None:
            shutil.rmtree(temp, ignore_errors=True)
