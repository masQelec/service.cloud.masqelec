# -*- coding: utf-8 -*-
"""Instalación exclusiva de snapshots y unidades; no ejecuta systemd.

Usar solo tras un journal privado durable y con todos los escritores de
la cuenta antigua detenidos. Destino existente/symlink se bloquea.
El contenido fuente nunca se muestra ni se convierte en texto en logs.
"""
import os
import stat
import tempfile


def _trusted_folder(folder):
    meta = os.lstat(folder)
    mode = stat.S_IMODE(meta.st_mode)
    # CoreELEC ships /storage/.config/system.d as root:root 0775.
    # Group 'root' is privileged, so ONLY that exact systemd directory may
    # retain its default group-write bit. All private OAuth directories,
    # drop-ins, symlinks and other paths keep the strict nonwritable rule.
    coreelec_systemd = (
        folder == "/storage/.config/system.d"
        and os.geteuid() == 0
        and meta.st_uid == 0
        and meta.st_gid == 0
        and mode in (0o755, 0o775)
    )
    if (not stat.S_ISDIR(meta.st_mode)
            or meta.st_uid != os.geteuid()
            or (mode & 0o022 and not coreelec_systemd)):
        raise ValueError("Unsafe install directory")


def _fsync_dir(folder):
    fd = os.open(folder, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def install_exclusive(path, content, mode):
    """Crea sin pisar ficheros existentes, con datos durables y permisos."""
    if (not isinstance(content, bytes)
            or not content or len(content) > 1024 * 1024
            or mode not in (0o600, 0o644)):
        raise ValueError("Invalid candidate artifact")
    folder, filename = os.path.dirname(path), os.path.basename(path)
    if (not filename or filename.startswith(".")
            or os.path.normpath(path) != path):
        raise ValueError("Unsafe artifact path")
    _trusted_folder(folder)
    if os.path.lexists(path):
        raise FileExistsError("Artifact already exists")
    fd, tmp = tempfile.mkstemp(prefix=".candidate-", dir=folder)
    linked = False
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb", closefd=False) as f:
            f.write(content)
            f.flush()
        os.fsync(fd)
        # Enlace duro evita sobrescribir si aparece otra versión entre
        # comprobación de no existencia e instalación.
        os.link(tmp, path, follow_symlinks=False)
        linked = True
        _fsync_dir(folder)
        return True
    finally:
        os.close(fd)
        if os.path.lexists(tmp):
            os.unlink(tmp)
        # Tras crear fichero y fallar fsync de directorio, conservar el
        # artefacto para revisión: no suponer que se puede desinstalar.
        if linked:
            pass


def remove_if_identical(path, expected):
    """Retirada conservadora SOLO de artefactos propios idénticos.

    Un rclone.conf aislado puede renovarse en marcha; nunca llamarlo con
    config de una cuenta en la que hubo escritor sin reconciliar tokens.
    """
    folder = os.path.dirname(path)
    _trusted_folder(folder)
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or
            info.st_uid != os.geteuid()
            or info.st_size != len(expected)):
        raise ValueError("Artifact changed")
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        if os.read(fd, 1024 * 1024 + 1) != expected:
            raise ValueError("Artifact changed")
    finally:
        os.close(fd)
    latest = os.lstat(path)
    if ((info.st_dev, info.st_ino, info.st_mtime_ns, info.st_ctime_ns) !=
            (latest.st_dev, latest.st_ino,
             latest.st_mtime_ns, latest.st_ctime_ns)):
        raise ValueError("Artifact changed concurrently")
    os.unlink(path)
    _fsync_dir(folder)
    return True
