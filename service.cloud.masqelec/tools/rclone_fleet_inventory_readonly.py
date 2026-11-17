# -*- coding: utf-8 -*-
"""P0-C2: inventario LOCAL y SOLO LECTURA de procesos rclone /proc.

Nunca abre rclone.conf, nunca invoca rclone ni lee keys/MQC2, no consulta
ninguna red y NUNCA declara coordinación de la flota. Solo imprime recuentos
anonimizados; ni argumentos ni URLs/token/string de /proc llegan a stdout.
Una muestra puntual no demuestra ausencia de otros escritores o reinicios.
"""
import os
import sys

_MAX_CMD = 16384
_PROC = "/proc"


def classify_args(args):
    """(es_rclone, es_mount, cuenta) cuenta=0/1 o None (ambigua)."""
    if not args or not os.path.basename(args[0]).startswith("rclone"):
        return False, False, None
    mount = any(x in ("mount", "mount2", "cmount") for x in args[1:])
    if not mount:
        return True, False, None
    names = set()
    for value in args[1:]:
        if not isinstance(value, str):
            continue
        if value.startswith(("users_library_1:", "library_1:")):
            names.add(0)
        if value.startswith(("users_library_2:", "library_2:")):
            names.add(1)
    if len(names) != 1:
        return True, True, None
    return True, True, next(iter(names))


def local_snapshot():
    """Dict de contadores, never raw argv. Inaccesible/truncado = unknown."""
    counters = {
        "rclone": 0, "mounts": 0, "account1": 0, "account2": 0,
        "unclassified": 0, "unreadable": 0,
    }
    try:
        iterator = os.scandir(_PROC)
    except OSError:
        return None
    try:
        for entry in iterator:
            if not entry.name.isdecimal() or int(entry.name) == os.getpid():
                continue
            try:
                with open(entry.path + "/cmdline", "rb") as f:
                    raw = f.read(_MAX_CMD + 1)
            except (FileNotFoundError, ProcessLookupError):
                continue  # Proceso desaparecido, muestra no atómica.
            except OSError:
                counters["unreadable"] += 1
                continue
            if len(raw) > _MAX_CMD or (raw and not raw.endswith(b"\0")):
                counters["unreadable"] += 1
                continue
            argv = [x.decode("utf-8", "replace")
                    for x in raw.split(b"\0") if x]
            is_rclone, is_mount, account = classify_args(argv)
            if not is_rclone:
                continue
            counters["rclone"] += 1
            if is_mount:
                counters["mounts"] += 1
            if is_mount and account == 0:
                counters["account1"] += 1
            elif is_mount and account == 1:
                counters["account2"] += 1
            else:
                counters["unclassified"] += 1
    finally:
        iterator.close()
    return counters


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv != ["--local-readonly"]:
        print("LAB_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=LOCAL_RCLONE_PROCESS_INVENTORY_READONLY")
    print("CONFIG_READ=NO")
    print("OAUTH_REQUEST=NO")
    print("NETWORK_REQUEST=NO")
    print("MOUNT_CHANGE=NO")
    print("SYSTEMD_WRITE=NO")
    print("GITHUB_UPLOAD=NO")
    data = local_snapshot()
    if data is None:
        print("PROC_SCAN=INCOMPLETE")
        print("FLEET_INVENTORY_AUTHENTICATED=NO")
        print("LAB_RESULT=BLOCKED_PROC_UNAVAILABLE")
        return 2
    print("OBSERVED_RCLONE_PROCESSES=" + str(data["rclone"]))
    print("OBSERVED_RCLONE_MOUNTS=" + str(data["mounts"]))
    print("OBSERVED_ACCOUNT_1_MOUNTS=" + str(data["account1"]))
    print("OBSERVED_ACCOUNT_2_MOUNTS=" + str(data["account2"]))
    print("OBSERVED_UNCLASSIFIED_RCLONE=" + str(data["unclassified"]))
    print("PROC_SCAN=" + (
        "INCOMPLETE" if data["unreadable"] else "SNAPSHOT_ONLY"))
    print("FLEET_INVENTORY_AUTHENTICATED=NO")
    print("REMOTE_CLIENTS_CHECKED=NO")
    print("LIVE_REFRESH_WRITERS_EXCLUDED=NO")
    print("LAB_RESULT=BLOCKED_FLEET_NOT_VERIFIED")
    return 2


if __name__ == "__main__":
    sys.exit(main())
