# -*- coding: utf-8 -*-
"""Selección de staging rápido y publicación atómica entre sistemas de archivos.

El staging puede vivir en tmpfs (/tmp). Los archivos finales y los respaldos
deben permanecer en /storage, incluso si el dispositivo se reinicia.
"""
import os
import shutil
import tempfile

MIN_TMP_FREE_BYTES = 128 * 1024 * 1024


def select_staging_base(preferred="/tmp", fallback="/storage/.catalog",
                        min_free_bytes=MIN_TMP_FREE_BYTES):
    """Utiliza /tmp si es escribible y dispone del margen mínimo."""
    os.makedirs(fallback, exist_ok=True)
    try:
        if (os.path.isdir(preferred) and
                os.access(preferred, os.W_OK | os.X_OK) and
                shutil.disk_usage(preferred).free >= int(min_free_bytes)):
            return preferred
    except (OSError, ValueError, TypeError):
        pass
    return fallback


def publish_file_atomic(src, dst):
    """Copia dentro del FS destino, fsync y reemplaza atómicamente.

    No se llama os.replace directamente desde /tmp a /storage: en sistemas
    de archivos diferentes podría fallar con EXDEV.
    """
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    target_dir = os.path.dirname(os.path.abspath(dst))
    os.makedirs(target_dir, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".masqelec-publish-", dir=target_dir)
    try:
        with os.fdopen(fd, "wb") as destination:
            with open(src, "rb") as source:
                shutil.copyfileobj(source, destination, length=256 * 1024)
            destination.flush()
            os.fsync(destination.fileno())
        if os.path.getsize(temp_path) != os.path.getsize(src):
            raise IOError("Copia incompleta durante publicación")
        os.replace(temp_path, dst)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
