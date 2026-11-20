# -*- coding: utf-8 -*-
"""Verificaciones del catálogo antes de modificar archivos del cliente.

No depende de Kodi ni de librerías externas.
El hash corresponde a la concatenación histórica de ruta relativa + contenido
para cada archivo .strm, ordenados lexicográficamente por ruta.
"""
import hashlib
import os
import re
import zipfile

MAX_ZIP_MEMBERS = 200000
MAX_STRM_SIZE = 1024 * 1024
MAX_ZIP_EXTRACTED_BYTES = 512 * 1024 * 1024
MAX_DELETE_FRACTION = 0.25
MIN_DELETE_ALLOWANCE = 10


def compute_catalog_hash(root):
    files = []
    for base, _, names in os.walk(root):
        for name in names:
            if name.endswith(".strm"):
                full = os.path.join(base, name)
                rel = os.path.relpath(full, root).replace("\\", "/")
                files.append((rel, full))
    files.sort(key=lambda item: item[0])
    digest = hashlib.sha256()
    for rel, full in files:
        digest.update(rel.encode("utf-8"))
        with open(full, "rb") as stream:
            for block in iter(lambda: stream.read(262144), b""):
                digest.update(block)
    return digest.hexdigest(), len(files)


def verify_staging(root, remote_version):
    if not isinstance(remote_version, str) or not remote_version.strip():
        raise ValueError("catalog.version ausente")
    tokens = remote_version.split()
    expected = tokens[0].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Hash inválido en catalog.version")
    count_match = re.search(r"\bstrm_files=(\d+)\b", remote_version)
    if not count_match:
        raise ValueError("catalog.version sin strm_files")
    expected_count = int(count_match.group(1))
    digest, actual_count = compute_catalog_hash(root)
    if actual_count == 0:
        raise ValueError("Catálogo vacío")
    if actual_count != expected_count:
        raise ValueError(
            "Cantidad STRM no coincide: esperado={} recibido={}".format(
                expected_count, actual_count))
    if digest != expected:
        raise ValueError("Hash de STRM no coincide con catalog.version")
    return actual_count


def validate_catalog_zip(zip_path):
    count = 0
    total_size = 0
    known = set()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            name = member.filename.replace("\\", "/")
            parts = name.split("/")
            if (name.startswith("/") or len(parts) < 2 or
                    any(part in ("", ".", "..") for part in parts) or
                    parts[0] not in ("videos", "tvshows") or
                    not name.endswith(".strm")):
                raise ValueError("Ruta ZIP inválida: {}".format(name))
            if name in known:
                raise ValueError("Entrada ZIP duplicada: {}".format(name))
            known.add(name)
            count += 1
            total_size += member.file_size
            if (member.file_size > MAX_STRM_SIZE or
                    count > MAX_ZIP_MEMBERS or
                    total_size > MAX_ZIP_EXTRACTED_BYTES):
                raise ValueError("ZIP supera los límites seguros")
    if count == 0:
        raise ValueError("ZIP sin archivos STRM")
    return count


def validate_deletions(local_count, deletion_count):
    """Fail-closed ante borrados masivos. Una retirada legítima requiere revisión."""
    if deletion_count <= 0:
        return
    if local_count <= 0:
        raise ValueError("No pueden borrarse archivos sin catálogo local")
    limit = max(MIN_DELETE_ALLOWANCE, int(local_count * MAX_DELETE_FRACTION))
    if deletion_count > limit:
        raise ValueError(
            "Borrado masivo bloqueado: {} de {} STRM (límite {})".format(
                deletion_count, local_count, limit))

def verify_zip_manifest(zip_path, version_text):
    """Valida ZIP completo y compara su contenido con catalog.version.

    La lectura con ZipFile.open verifica también el CRC de los miembros.
    No extrae nada al sistema de archivos.
    """
    entries = validate_catalog_zip(zip_path)
    tokens = (version_text or "").split()
    expected = tokens[0].lower() if tokens else ""
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ValueError("Hash inválido en catalog.version")
    match = re.search(r"\bstrm_files=(\d+)\b", version_text or "")
    if not match or int(match.group(1)) != entries:
        raise ValueError("Número STRM ZIP/version no coincide")

    h = hashlib.sha256()
    with zipfile.ZipFile(zip_path, "r") as archive:
        for name in sorted(member.filename.replace("\\", "/") for member in archive.infolist() if not member.is_dir()):
            h.update(name.encode("utf-8"))
            with archive.open(name, "r") as stream:
                for chunk in iter(lambda: stream.read(262144), b""):
                    h.update(chunk)
    if h.hexdigest() != expected:
        raise ValueError("Hash del ZIP no coincide con catalog.version")
    return entries
