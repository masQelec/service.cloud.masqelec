# -*- coding: utf-8 -*-
"""Aplicación protegida de un catálogo MASTER ya generado y validado.

Prepara una copia de seguridad de los STRM modificados/eliminados ANTES de
cualquier cambio. Restaura ante errores normales de E/S; los cortes abruptos
de corriente siguen requiriendo recuperación explícita.
Solo actúa bajo los subárboles videos/ y tvshows/.
"""
import hashlib
import os
import shutil
import uuid

from lib import catalog_safety


def _list_strm(root):
    result = {}
    for category in ("videos", "tvshows"):
        base = os.path.join(root, category)
        if not os.path.isdir(base):
            continue
        for folder, dirs, names in os.walk(base, followlinks=False):
            if os.path.islink(folder):
                raise ValueError("Directorio simbólico no permitido: {}".format(folder))
            for directory in dirs:
                if os.path.islink(os.path.join(folder, directory)):
                    raise ValueError("Directorio simbólico no permitido: {}".format(directory))
            for name in names:
                if not name.endswith(".strm"):
                    continue
                full = os.path.join(folder, name)
                if os.path.islink(full) or not os.path.isfile(full):
                    raise ValueError("STRM no regular: {}".format(full))
                rel = os.path.relpath(full, root).replace("\\", "/")
                result[rel] = full
    return result


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(262144), b""):
            h.update(chunk)
    return h.hexdigest()


def _replace_from_stage(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    temp = dst + ".new-" + uuid.uuid4().hex
    try:
        shutil.copy2(src, temp)
        os.replace(temp, dst)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def _cleanup_empty_dirs(root):
    if not os.path.isdir(root):
        return
    for base, dirs, files in os.walk(root, topdown=False):
        if base == root:
            continue
        if not dirs and not files:
            try:
                os.rmdir(base)
            except OSError:
                pass


def apply_staged_catalog(stage_root, live_root, backup_root):
    """Aplica el catálogo verificado. Retorna (copiados, eliminados).

    - Bloquea borrados superiores al 25% (mínimo diez archivos tolerados).
    - Copia primero; solo borra tras completar TODAS las copias.
    - Realiza rollback de cambios si falla una operación.
    - No publica por sí misma catalog.version ni catalog.zip.
    """
    staged = _list_strm(stage_root)
    if not staged:
        raise ValueError("Catálogo MASTER vacío: se conserva la versión anterior")
    existing = _list_strm(live_root)
    # Si Kodi devuelve temporalmente una categoría vacía, no se destruye
    # el catálogo anterior. Una eliminación total legítima requiere revisión.
    for category in ("videos", "tvshows"):
        prefix = category + "/"
        old_count = sum(rel.startswith(prefix) for rel in existing)
        new_count = sum(rel.startswith(prefix) for rel in staged)
        if old_count and not new_count:
            raise ValueError(
                "MASTER: categoría {} vacía ({}) - borrado bloqueado".format(
                    category, old_count))
    if existing and len(staged) * 2 < len(existing):
        raise ValueError("MASTER: reducción superior al 50% bloqueada")
    deleted = sorted(set(existing) - set(staged))
    catalog_safety.validate_deletions(len(existing), len(deleted))

    to_copy = []
    for rel in sorted(staged):
        old = existing.get(rel)
        if old is None or _sha256(old) != _sha256(staged[rel]):
            to_copy.append(rel)

    os.makedirs(backup_root, exist_ok=True)
    victims = sorted(set(deleted) | (set(to_copy) & set(existing)))
    for rel in victims:
        target = os.path.join(backup_root, rel.replace("/", os.sep))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(existing[rel], target)

    # Esta lista contiene únicamente operaciones confirmadas en el disco.
    completed = []
    try:
        for rel in to_copy:
            dst = os.path.join(live_root, rel.replace("/", os.sep))
            _replace_from_stage(staged[rel], dst)
            completed.append(("write", rel))

        for rel in deleted:
            os.remove(existing[rel])
            completed.append(("delete", rel))
    except Exception as error:
        rollback_errors = []
        for operation, rel in reversed(completed):
            dest = os.path.join(live_root, rel.replace("/", os.sep))
            try:
                if rel in existing:
                    saved = os.path.join(backup_root, rel.replace("/", os.sep))
                    _replace_from_stage(saved, dest)
                elif operation == "write" and os.path.exists(dest):
                    os.remove(dest)
            except Exception as rollback_error:
                rollback_errors.append("{}: {}".format(rel, rollback_error))
        if rollback_errors:
            raise RuntimeError(
                "Aplicación fallida ({}) y rollback INCOMPLETO: {}".format(
                    error, "; ".join(rollback_errors))) from error
        raise RuntimeError("Aplicación fallida; rollback completado: {}".format(error)) from error

    for category in ("videos", "tvshows"):
        _cleanup_empty_dirs(os.path.join(live_root, category))
    return len(to_copy), len(deleted)
