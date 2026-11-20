# -*- coding: utf-8 -*-
"""Elige dos muestras desde los .strm LOCALES de KodiELEC, sin acceder a FUSE.

MASTER/CLIENTE usan /storage/videos y /storage/tvshows para el catálogo.
Nunca lee medios en el descubrimiento: solo archivos .strm regulares, sin
symlinks y de tamaño limitado. Corta si el catálogo es demasiado grande.
Las rutas seleccionadas NO deben aparecer en logs.
"""
import os
import stat
import time
import sys

CATALOG_ROOTS = ("/storage/videos", "/storage/tvshows")
SAMPLE_PREFIXES = {
    1: ("/storage/.mnt/videos/1/", "/storage/.mnt/tvshows/1/"),
    2: ("/storage/.mnt/videos/2/", "/storage/.mnt/tvshows/2/"),
}
MAX_FILES = 200000
MAX_SECONDS = 12
MAX_DEPTH = 8
MAX_STRM_BYTES = 8192


def _media_account(raw):
    """Un .strm solo contiene una ruta LOCAL permitida, nunca una URL."""
    try:
        if type(raw) is not bytes or not 1 <= len(raw) <= MAX_STRM_BYTES:
            return None
        value = raw.decode("utf-8", "strict").rstrip("\r\n")
        if (not value or "\n" in value or "\r" in value or
                "\0" in value or not value.startswith("/storage/.mnt/") or
                os.path.normpath(value) != value):
            return None
        for account, prefixes in SAMPLE_PREFIXES.items():
            if any(value.startswith(prefix) and
                   len(value) > len(prefix) for prefix in prefixes):
                return account, value
    except (UnicodeError, ValueError, TypeError):
        pass
    return None


def _local_strm_value(path):
    """Lectura acotada de un archivo regular no-symlink, detecta carreras."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or
                not 0 < before.st_size <= MAX_STRM_BYTES):
            return None
        with os.fdopen(fd, "rb", closefd=False) as stream:
            raw = stream.read(MAX_STRM_BYTES + 1)
        after = os.fstat(fd)
        if (raw is None or len(raw) != before.st_size or
                (before.st_dev, before.st_ino, before.st_mtime_ns,
                 before.st_ctime_ns) !=
                (after.st_dev, after.st_ino, after.st_mtime_ns,
                 after.st_ctime_ns)):
            return None
        return _media_account(raw)
    finally:
        os.close(fd)


def discover(roots=CATALOG_ROOTS, *, max_files=MAX_FILES,
             max_seconds=MAX_SECONDS):
    """Devuelve (media_1, media_2) o None; no estado parcial ni escrituras.

    No sigue symlinks de carpetas. Si no hay dos muestras completas o se
    alcanza cualquier límite, no permite una migración desatendida.
    """
    if (not isinstance(roots, (tuple, list)) or not 1 <= len(roots) <= 4
            or type(max_files) is not int or max_files < 1
            or type(max_seconds) not in (int, float) or max_seconds <= 0):
        return None
    result = {}
    visited = 0
    deadline = time.monotonic() + max_seconds
    try:
        for root in roots:
            if type(root) is not str or not os.path.isabs(root):
                return None
            info = os.lstat(root)
            if not stat.S_ISDIR(info.st_mode):
                return None
            if os.path.islink(root):
                return None
            pending = [(root, 0)]
            while pending:
                if time.monotonic() >= deadline:
                    return None
                folder, depth = pending.pop()
                if depth > MAX_DEPTH:
                    return None  # Catálogo inesperado, no migrar.
                with os.scandir(folder) as entries:
                    for entry in entries:
                        visited += 1
                        if visited > max_files or time.monotonic() >= deadline:
                            return None
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append((entry.path, depth + 1))
                            continue
                        if (not entry.name.lower().endswith(".strm") or
                                not entry.is_file(follow_symlinks=False)):
                            continue
                        item = _local_strm_value(entry.path)
                        if item is None:
                            continue
                        account, media = item
                        if account not in result:
                            result[account] = media
                        if set(result) == {1, 2}:
                            return result[1], result[2]
        return None
    except (OSError, ValueError, UnicodeError):
        return None


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--inventory"]:
        print("MEDIA_DISCOVERY_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=LOCAL_STRM_MEDIA_SAMPLES_READ_ONLY")
    print("ONEDRIVE_ACCESSED=NO")
    print("FUSE_OR_SYSTEMD_CHANGED=NO")
    print("OAUTH_CONFIG_READ=NO")
    print("STRM_FILES_CHANGED=NO")
    print("MEDIA_PATHS_PRINTED=NO")
    result = discover()
    print("ACCOUNT_1_SAMPLE=" + ("FOUND" if result else "NOT_VERIFIED"))
    print("ACCOUNT_2_SAMPLE=" + ("FOUND" if result else "NOT_VERIFIED"))
    print("REAL_OAUTH_PROBE_ALLOWED=NO")
    print("CUTOVER_AUTHORIZED=NO")
    print("MEDIA_DISCOVERY_RESULT=" + (
        "PASS_2_LOCAL_STRM_ACCOUNTS" if result
        else "BLOCKED_NO_TWO_LOCAL_SAMPLES"))
    return 0 if result else 2


if __name__ == "__main__":
    sys.exit(main())
