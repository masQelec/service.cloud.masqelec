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


def check_two_fuse_four_bind(mountinfo):
    """Verifica relación real entre montajes (no basta que existan rutas).

    Los cuatro targets legacy deben apuntar, por dispositivo, al mismo
    superblock del FUSE raíz y a la subcarpeta exacta.
    """
    entries = mount_entries(mountinfo)
    for i, fuse_root in enumerate(plan.FUSE_ROOTS):
        root = entries.get(fuse_root)
        if root is None or root["fstype"] != "fuse.rclone":
            return False
        for _, source_index, folder, target in plan.BIND_MAP:
            if source_index != i:
                continue
            child = entries.get(target)
            if child is None:
                return False
            expected_root = root["fsroot"].rstrip("/") + "/" + folder
            if child["fsroot"] != expected_root:
                return False
            if any(child[field] != root[field] for field in (
                    "device", "fstype", "source")):
                return False
    return True
