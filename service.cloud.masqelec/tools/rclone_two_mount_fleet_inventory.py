# -*- coding: utf-8 -*-
"""Inventario LOCAL de escritores rclone/OAuth para MASTER y CLIENTES.

Solo lee /proc/PID/comm, /proc/PID/cmdline y /proc/self/mountinfo.
No lee configuraciones ni credenciales, NO ejecuta rclone, no llama red
ni PIDs ni nombres de cuenta. No modifica montajes ni systemd.

Un resultado PASS_READ_ONLY significa inventario local legible, NUNCA
autorización de probe OAuth ni coordinación de otros dispositivos.
"""
import errno
import os
import re
import sys

MAX_CMDLINE = 32768
MAX_MOUNTINFO = 4 * 1024 * 1024
EXPECTED_LEGACY = (
    "/storage/.mnt/videos/1", "/storage/.mnt/videos/2",
    "/storage/.mnt/tvshows/1", "/storage/.mnt/tvshows/2",
)
EXPECTED_V2 = ("/storage/.mnt/cloud/1", "/storage/.mnt/cloud/2")
KNOWN_ROOTS = set(EXPECTED_LEGACY + EXPECTED_V2)


def _read_limited(path, limit):
    with open(path, "rb") as source:
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Oversized local metadata")
    return data


def _is_gone(exc):
    return isinstance(exc, OSError) and exc.errno in (
        errno.ENOENT, errno.ESRCH)


def inspect_processes(proc_root="/proc"):
    """Cuenta solo procesos rclone observados, sin exponer sus argumentos.

    Un rclone de modo no-mount TAMBIÉN puede renovar credenciales OAuth.
    Si no puede leerse un proceso, se marca incompleto. Los procesos
    desaparecidos durante el recorrido son carreras esperables.
    """
    result = {"rclone": 0, "mount": 0, "other": 0,
              "uncertain": 0, "complete": True}
    try:
        with os.scandir(proc_root) as entries:
            for entry in entries:
                if not entry.name.isdecimal():
                    continue
                base = os.path.join(proc_root, entry.name)
                try:
                    comm = _read_limited(os.path.join(base, "comm"), 255)
                except OSError as exc:
                    if not _is_gone(exc):
                        result["complete"] = False
                    continue
                except ValueError:
                    result["complete"] = False
                    continue
                if not comm.strip().startswith(b"rclone"):
                    continue
                result["rclone"] += 1
                try:
                    raw = _read_limited(
                        os.path.join(base, "cmdline"), MAX_CMDLINE)
                    args = [x for x in raw.split(b"\0") if x]
                    if not args:
                        result["uncertain"] += 1
                        result["complete"] = False
                        continue
                    first = args[0].rsplit(b"/", 1)[-1]
                    if not first.startswith(b"rclone"):
                        result["uncertain"] += 1
                        result["complete"] = False
                    elif any(arg in (b"mount", b"mount2", b"cmount")
                             for arg in args[1:]):
                        result["mount"] += 1
                    else:
                        result["other"] += 1
                except (OSError, ValueError):
                    result["uncertain"] += 1
                    result["complete"] = False
    except (OSError, ValueError):
        result["complete"] = False
    return result


_ESC = re.compile(r"\\([0-7]{3})")


def _mount_path(text):
    return _ESC.sub(lambda match: chr(int(match.group(1), 8)), text)


def inspect_mounts(raw):
    """Cuenta FUSE según mountinfo; no consulta el contenido de OneDrive."""
    result = {"legacy": 0, "new": 0, "extra_fuse": 0,
              "stacked": 0, "fuse_total": 0, "complete": False}
    try:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "strict")
        if not isinstance(raw, str) or not raw or len(raw) > MAX_MOUNTINFO:
            return result
        counts = {}
        fstype_by_path = {}
        for line in raw.splitlines():
            left, separator, right = line.partition(" - ")
            a = left.split()
            b = right.split()
            if not separator or len(a) < 6 or len(b) < 3:
                return result
            point = _mount_path(a[4])
            counts[point] = counts.get(point, 0) + 1
            fstype_by_path[point] = b[0]
            if b[0] == "fuse.rclone":
                result["fuse_total"] += 1
                if point not in KNOWN_ROOTS:
                    result["extra_fuse"] += 1
        result["legacy"] = sum(
            counts.get(path, 0) == 1 and
            fstype_by_path.get(path) == "fuse.rclone"
            for path in EXPECTED_LEGACY)
        result["new"] = sum(
            counts.get(path, 0) == 1 and
            fstype_by_path.get(path) == "fuse.rclone"
            for path in EXPECTED_V2)
        result["stacked"] = sum(counts.get(path, 0) > 1
                                for path in KNOWN_ROOTS)
        result["complete"] = True
    except (UnicodeError, TypeError, ValueError):
        pass
    return result


def inventory(proc_root="/proc", mountinfo_path="/proc/self/mountinfo"):
    processes = inspect_processes(proc_root)
    try:
        mounts = inspect_mounts(_read_limited(
            mountinfo_path, MAX_MOUNTINFO))
    except (OSError, ValueError):
        mounts = inspect_mounts(None)
    return processes, mounts


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args != ["--inventory"]:
        print("INVENTORY_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=FLEET_OAUTH_LOCAL_INVENTORY_READ_ONLY")
    print("REMOTE_REQUESTS=NO")
    print("CANONICAL_CONFIG_READ=NO")
    print("TOKEN_VALUES_PRINTED=NO")
    print("COMMAND_LINE_INSPECTED=YES_LOCAL_ONLY")
    print("PROCESS_ARGUMENTS_PRINTED=NO")
    print("MOUNT_OR_SYSTEMD_MUTATIONS=NO")
    print("DEVICE_ROLE=NOT_ATTESTED")
    running_as_root = os.geteuid() == 0
    print("ROOT=" + ("YES" if running_as_root else "NO"))
    processes, mounts = inventory()
    print("PROC_INSPECTION=" + (
        "COMPLETE" if processes["complete"] else "INCOMPLETE"))
    print("MOUNTINFO_INSPECTION=" + (
        "COMPLETE" if mounts["complete"] else "INCOMPLETE"))
    print("RCLONE_PROCESSES=" + str(processes["rclone"]))
    print("RCLONE_MOUNT_PROCESSES=" + str(processes["mount"]))
    print("RCLONE_OTHER_PROCESSES=" + str(processes["other"]))
    print("RCLONE_UNCLASSIFIED=" + str(processes["uncertain"]))
    print("RCLONE_FUSE_MOUNTS=" + str(mounts["fuse_total"]))
    print("LEGACY_MOUNT_TARGETS={}/4".format(mounts["legacy"]))
    print("V2_FUSE_ROOTS={}/2".format(mounts["new"]))
    print("STACKED_KODI_OR_V2_TARGETS=" + str(mounts["stacked"]))
    print("OTHER_RCLONE_FUSE_MOUNTS=" + str(mounts["extra_fuse"]))
    print("SINGLE_SNAPSHOT_STABILITY=NOT_VERIFIED")
    print("OTHER_DEVICES_INSPECTED=NO")
    print("FLEET_OAUTH_COORDINATION=NOT_VERIFIED")
    print("REAL_OAUTH_PROBE_ALLOWED=NO")
    print("CUTOVER_AUTHORIZED=NO")
    # Sin root, un /proc filtrado (hidepid) puede omitir escritores.
    # Nunca declarar inventario completo si no se puede ver la máquina.
    good = running_as_root and processes["complete"] and mounts["complete"]
    print("INVENTORY_RESULT=" + (
        "PASS_READ_ONLY" if good else "BLOCKED_INCOMPLETE_LOCAL_INSPECTION"))
    return 0 if good else 2


if __name__ == "__main__":
    sys.exit(main())
