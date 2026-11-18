# -*- coding: utf-8 -*-
"""Comprueba 2 montajes FUSE + 4 bind con /proc/self/mountinfo.

No ejecuta mount, umount, systemctl ni operaciones de red.
"""
import re

from lib import rclone_two_mount_plan as plan

_OCTAL = re.compile(r"\\([0-7]{3})")


def _decode(value):
    return _OCTAL.sub(lambda m: chr(int(m.group(1), 8)), value)


def mount_entries(data):
    """Última entrada por destino (Linux permite montajes apilados)."""
    if isinstance(data, bytes):
        data = data.decode("utf-8", "strict")
    if not isinstance(data, str):
        raise TypeError("mountinfo debe ser texto")
    entries = {}
    for line in data.splitlines():
        start, sep, end = line.partition(" - ")
        if not sep:
            raise ValueError("mountinfo sin separador")
        left, right = start.split(), end.split()
        if len(left) < 6 or len(right) < 3:
            raise ValueError("mountinfo truncado")
        name = _decode(left[4])
        entries[name] = {
            "device": left[2],
            "fsroot": _decode(left[3]),
            "fstype": right[0],
            "source": _decode(right[1]),
        }
    return entries


def check_layout_at(mountinfo, fuse_roots, bind_map):
    """Verificador configurable para laboratorio aislado; no monta nada.

    fuse_roots=(raíz1, raíz2); bind_map=(índice, carpeta, destino) por
    cada una de las cuatro carpetas. No se acepta resultado basado solo
    en directorios existentes: se exige superblock y fsroot de mountinfo.
    """
    if (not isinstance(fuse_roots, (tuple, list)) or len(fuse_roots) != 2
            or len(set(fuse_roots)) != 2 or
            not isinstance(bind_map, (tuple, list)) or len(bind_map) != 4):
        return False
    try:
        entries = mount_entries(mountinfo)
    except (ValueError, TypeError, UnicodeError):
        return False
    used = set()
    counts = [0, 0]
    folders = [set(), set()]
    for item in bind_map:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            return False
        i, folder, target = item
        if (type(i) is not int or i not in (0, 1)
                or folder not in ("movies", "tvshows")
                or not isinstance(target, str) or target in used
                or target in fuse_roots):
            return False
        if folder in folders[i]:
            return False
        used.add(target)
        folders[i].add(folder)
        counts[i] += 1
        root = entries.get(fuse_roots[i])
        child = entries.get(target)
        if (root is None or child is None
                or root["fstype"] != "fuse.rclone"):
            return False
        expected = root["fsroot"].rstrip("/") + "/" + folder
        if child["fsroot"] != expected:
            return False
        if any(child[field] != root[field] for field in (
                "device", "fstype", "source")):
            return False
    return counts == [2, 2] and folders == [
        {"movies", "tvshows"}, {"movies", "tvshows"}]


def check_two_fuse_four_bind(mountinfo):
    """Valida rutas Kodi; preserva ValueError del parser legacy estricto."""
    # Los consumidores existentes distinguen un mountinfo truncado
    # (excepción) de un layout incompleto pero bien formado (False).
    mount_entries(mountinfo)
    bind_map = [(index, folder, target)
                for _, index, folder, target in plan.BIND_MAP]
    return check_layout_at(mountinfo, plan.FUSE_ROOTS, bind_map)
