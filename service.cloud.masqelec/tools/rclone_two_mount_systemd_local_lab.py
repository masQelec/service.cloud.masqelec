# -*- coding: utf-8 -*-
"""KodiELEC: 2 rclone FUSE + 4 bind con systemd REAL, backend LOCAL aislado.

Autocontenido para /tmp, NO importar librerías del addon instalado.
--preflight: SOLO LECTURA. --run-isolated-systemd --confirm-isolated-only:
crea seis unidades con nombres ALEATORIOS exclusivamente en
/run/systemd/system, no las habilita, monta SOLO bajo /tmp/masqelec-sd-lab-*
y las borra tras comprobar que no queda ningún montaje ni servicio vivo.

No llama OAuth, no abre rclone.conf, no lee /storage/.mnt ni altera
MASTER/CLIENTE, addon, catálogo o las cuatro unidades de producción.
Si la limpieza no es demostrable deja las rutas para revisión MANUAL.
"""
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import time

TMP = "/tmp"
RUNTIME_UNITS = "/run/systemd/system"
PREFIX = "masqelec-sd-lab-"
SAMPLE = b"masqelec-systemd-local-fixture\n"
EXPECTED_TYPES = ("fuse.rclone", "fuse.rclone")


def _clean_env():
    return {k: v for k, v in os.environ.items()
            if not k.startswith(("RCLONE_", "ONEDRIVE_", "AWS_", "AZURE_",
                                 "GOOGLE_", "GDRIVE_"))}


def rclone_binary():
    for value in ("/storage/.config/rclone/rclone", "/usr/bin/rclone",
                  "/usr/local/bin/rclone"):
        if os.path.isfile(value) and os.access(value, os.X_OK):
            return value
    return shutil.which("rclone")


def _run(argv, timeout=30, output=False):
    p = subprocess.run(
        argv, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if output else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=timeout, check=False, env=_clean_env())
    return p.returncode == 0, p.stdout if output else b""


def _help(binary, args):
    if not binary:
        return b""
    try:
        ok, result = _run([binary] + args, timeout=12, output=True)
        return result if ok else b""
    except (OSError, subprocess.SubprocessError):
        return b""


def _rclone_ready(binary):
    mount_help = _help(binary, ["mount", "--help"])
    glob_help = _help(binary, ["help", "flags"])
    if b"--config" not in glob_help:
        glob_help = _help(binary, ["--help"])
    return (b"--read-only" in mount_help
            and b"--vfs-cache-mode" in mount_help
            and b"--config" in glob_help)


def _systemd_online():
    try:
        ok, _ = _run(
            ["systemctl", "list-units", "--type=service",
             "--all", "--no-pager", "--no-legend"], timeout=12)
        return ok
    except (OSError, subprocess.SubprocessError):
        return False


def _no_prior_lab():
    """No iniciar otro ensayo si queda una transacción anterior incompleta."""
    try:
        return (not any(name.startswith(PREFIX) for name in os.listdir(TMP))
                and not any(name.startswith(PREFIX)
                            for name in os.listdir(RUNTIME_UNITS)))
    except OSError:
        return False


def prerequisites():
    binary = rclone_binary()
    try:
        fuse = os.path.exists("/dev/fuse") and stat.S_ISCHR(
            os.stat("/dev/fuse").st_mode)
    except OSError:
        fuse = False
    return {
        "root": os.geteuid() == 0,
        "fuse": fuse,
        "rclone": binary is not None,
        "rclone_flags": _rclone_ready(binary),
        "systemctl": shutil.which("systemctl") is not None,
        "systemd_online": _systemd_online(),
        "no_prior_lab": _no_prior_lab(),
        "runtime_dir": (os.path.isdir(RUNTIME_UNITS)
                        and not os.path.islink(RUNTIME_UNITS)
                        and os.access(RUNTIME_UNITS, os.W_OK)),
        "mount": shutil.which("mount") is not None,
        "umount": shutil.which("umount") is not None,
        "mountpoint": shutil.which("mountpoint") is not None,
        "shell": os.path.isfile("/bin/sh"),
        "sleep": os.path.isfile("/bin/sleep"),
        "mountinfo": os.path.isfile("/proc/self/mountinfo"),
        "tmp": (os.path.realpath(TMP) == TMP
                and os.path.isdir(TMP)),
    }


def _identity(root):
    root = Path(root)
    if (root.parent != Path(TMP) or root.is_symlink()
            or not re.fullmatch(PREFIX + r"[a-f0-9]{16}", root.name)):
        raise ValueError("Lab root must have an isolated random name")
    return root.name


def _layout(root):
    _identity(root)
    root = Path(root)
    fuse = [str(root / "fuse" / str(i)) for i in (1, 2)]
    binds = [
        (index, folder, str(root / "bind" / group / str(index+1)))
        for group, folder in (("videos", "movies"), ("tvshows", "tvshows"))
        for index in (0, 1)
    ]
    fixtures = [root / "fixtures" / str(i) for i in (1, 2)]
    return fuse, binds, fixtures


def _unit_names(root):
    prefix = _identity(root)
    return {
        "fuse": [prefix + "-fuse{}.service".format(i) for i in (1, 2)],
        "bind": [prefix + "-bind-{}-{}.service".format(
            group, i) for group in ("videos", "tvshows") for i in (1, 2)],
    }


def _unit_files(root, rclone, *, mount_cmd="/bin/mount",
                umount_cmd="/bin/umount", mountpoint_cmd="/bin/mountpoint"):
    _identity(root)
    if not (rclone and os.path.isabs(rclone)
            and re.fullmatch(r"[/A-Za-z0-9._-]+", rclone)):
        raise ValueError("Unsafe rclone executable")
    for binary in (mount_cmd, umount_cmd, mountpoint_cmd):
        if not (os.path.isabs(binary)
                and re.fullmatch(r"[/A-Za-z0-9._-]+", binary)):
            raise ValueError("Unsafe mount binary")
    fuse, binds, fixtures = _layout(root)
    names = _unit_names(root)
    units = {}
    for index, (source, target) in enumerate(zip(fixtures, fuse)):
        units[names["fuse"][index]] = (
            "[Unit]\nDescription=masQelec ISOLATED systemd/FUSE lab\n"
            "[Service]\nType=simple\nRestart=no\n"
            "KillSignal=SIGINT\nTimeoutStopSec=20\n"
            "ExecStart={} mount {} {} --config /dev/null --read-only "
            "--vfs-cache-mode off\n"
            "ExecStop={} {}\n"
        ).format(rclone, source, target, umount_cmd, target).encode()
    for index, folder, target in binds:
        source = fuse[index] + "/" + folder
        group = "videos" if folder == "movies" else "tvshows"
        unit_name = names["bind"][
            (0 if group == "videos" else 2) + index]
        parent_unit = names["fuse"][index]
        # Type=simple -> systemctl start puede devolver antes del FUSE.
        wait = (
            "for x in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 "
            "16 17 18 19 20 21 22 23 24 25 26 27 28 29 30; "
            "do {} -q {} && [ -d {} ] && exit 0; "
            "/bin/sleep 1; done; exit 1"
        ).format(mountpoint_cmd, fuse[index], source)
        units[unit_name] = (
            "[Unit]\nDescription=masQelec ISOLATED systemd/bind lab\n"
            "BindsTo={}\nAfter={}\n"
            "[Service]\nType=oneshot\nRemainAfterExit=yes\n"
            "TimeoutStartSec=45\n"
            "ExecStartPre=/bin/sh -c '! {} -q {}'\n"
            "ExecStartPre=/bin/sh -c '{}'\n"
            "ExecStart={} --bind {} {}\n"
            "ExecStop={} {}\n"
        ).format(
            parent_unit, parent_unit, mountpoint_cmd, target, wait,
            mount_cmd, source, target, umount_cmd, target).encode()
    if len(units) != 6:
        raise ValueError("Expected exactly 6 units")
    forbidden = (b"/storage/.mnt", b"rclone.conf", b"users_library_",
                 b"Onedrive", b"RCLONE_CONFIG=")
    for content in units.values():
        if any(x in content for x in forbidden):
            raise ValueError("Production path or configuration in test unit")
    return units


def _read_mountinfo():
    with open("/proc/self/mountinfo", "r", encoding="utf-8") as source:
        return source.read(4 * 1024 * 1024 + 1)


def _decode(name):
    return re.sub(
        r"\\([0-7]{3})", lambda m: chr(int(m.group(1), 8)), name)


def _mount_records(text):
    records = {}
    for line in text.splitlines():
        left, sep, right = line.partition(" - ")
        a, b = left.split(), right.split()
        if not sep or len(a) < 6 or len(b) < 3:
            raise ValueError("Unexpected mountinfo record")
        dest = _decode(a[4])
        records.setdefault(dest, []).append(
            {"device": a[2], "fsroot": _decode(a[3]),
             "fstype": b[0], "source": _decode(b[1])})
    return records


def _check_mounts(text, root):
    try:
        fuse, binds, _ = _layout(root)
        entries = _mount_records(text)
        for point in fuse:
            if (len(entries.get(point, ())) != 1 or
                    entries[point][0]["fstype"] != "fuse.rclone"
                    or entries[point][0]["fsroot"] != "/"):
                return False
        if entries[fuse[0]][0]["device"] == entries[fuse[1]][0]["device"]:
            return False
        for index, folder, target in binds:
            if len(entries.get(target, ())) != 1:
                return False
            parent = entries[fuse[index]][0]
            child = entries[target][0]
            if child["fsroot"] != parent["fsroot"].rstrip("/") + "/" + folder:
                return False
            if any(child[key] != parent[key] for key in
                   ("device", "source", "fstype")):
                return False
        return True
    except (ValueError, TypeError, UnicodeError, IndexError):
        return False


def _any_lab_mounted(root):
    try:
        _identity(root)
        entries = _mount_records(_read_mountinfo())
        prefix = str(root) + "/"
        return any(path == str(root) or path.startswith(prefix)
                   for path in entries)
    except (OSError, ValueError, UnicodeError):
        # Mountinfo not readable => NEVER recursively delete /tmp.
        return True


def _is_active(unit):
    ok, _ = _run(["systemctl", "is-active", "--quiet", unit], timeout=8)
    return ok


def _control(op, unit=None, *, timeout=40):
    if op not in ("start", "stop", "daemon-reload", "reset-failed"):
        raise ValueError("systemd operation not permitted")
    if op == "daemon-reload":
        cmd = ["systemctl", op]
    else:
        if not (unit and re.fullmatch(
                PREFIX + r"[a-f0-9]{16}-(?:fuse[12]|bind-(?:videos|tvshows)-[12])\.service",
                unit)):
            raise ValueError("Not a lab service")
        cmd = ["systemctl", op, unit]
    ok, _ = _run(cmd, timeout=timeout)
    return ok


def _service_diagnostic(unit, root):
    """Metadatos de systemd ANTES de desmontar; nunca journal ni argumentos.

    Propiedades seleccionadas, sin ExecStart ni entorno. Compatible con
    systemd antiguo: campos no admitidos o ausentes => UNKNOWN.
    """
    names = _unit_names(root)
    order = names["fuse"] + names["bind"]
    stages = ("FUSE_1", "FUSE_2", "BIND_VIDEOS_1", "BIND_VIDEOS_2",
              "BIND_TVSHOWS_1", "BIND_TVSHOWS_2")
    if unit not in order:
        return {"FAILED_STAGE": "INVALID_LAB_UNIT",
                "FAILED_UNIT": "UNKNOWN"}
    values = {
        "FAILED_STAGE": stages[order.index(unit)],
        "FAILED_UNIT": unit,
        "SYSTEMD_LOAD": "UNKNOWN",
        "SYSTEMD_ACTIVE": "UNKNOWN",
        "SYSTEMD_SUBSTATE": "UNKNOWN",
        "SYSTEMD_RESULT": "UNKNOWN",
        "SYSTEMD_MAIN_STATUS": "UNKNOWN",
        "SYSTEMD_PRE_STATUS": "UNKNOWN",
        "SYSTEMD_DIAG_CLASS": "UNCLASSIFIED",
    }
    keys = {
        "LoadState": "SYSTEMD_LOAD",
        "ActiveState": "SYSTEMD_ACTIVE",
        "SubState": "SYSTEMD_SUBSTATE",
        "Result": "SYSTEMD_RESULT",
        "ExecMainStatus": "SYSTEMD_MAIN_STATUS",
    }
    try:
        argv = ["systemctl", "show", unit, "--no-pager"] + [
            "--property=" + key for key in (
                "LoadState", "ActiveState", "SubState", "Result",
                "ExecMainStatus", "ExecStartPre")]
        ok, raw = _run(argv, timeout=9, output=True)
        if ok and isinstance(raw, bytes) and len(raw) < 65536:
            metadata = raw.decode("utf-8", "replace")
            for line in metadata.splitlines():
                key, separator, value = line.partition("=")
                if not separator:
                    continue
                if key in keys and re.fullmatch(
                        r"[A-Za-z0-9_.:/-]{1,80}", value):
                    values[keys[key]] = value
                if key == "ExecStartPre":
                    matches = re.findall(r"\bstatus=([0-9]{1,4})\b",
                                         value)
                    if matches:
                        values["SYSTEMD_PRE_STATUS"] = matches[-1]
            if values["SYSTEMD_LOAD"] not in ("loaded", "UNKNOWN"):
                values["SYSTEMD_DIAG_CLASS"] = "UNIT_LOAD_FAILURE"
            elif values["SYSTEMD_RESULT"] in (
                    "dependency", "timeout", "start-limit-hit"):
                values["SYSTEMD_DIAG_CLASS"] = {
                    "dependency": "DEPENDENCY_FAILURE",
                    "timeout": "START_TIMEOUT",
                    "start-limit-hit": "START_LIMIT",
                }[values["SYSTEMD_RESULT"]]
            elif values["SYSTEMD_PRE_STATUS"] not in ("0", "UNKNOWN"):
                values["SYSTEMD_DIAG_CLASS"] = "EXECSTARTPRE_FAILURE"
            elif values["SYSTEMD_MAIN_STATUS"] == "203":
                values["SYSTEMD_DIAG_CLASS"] = "EXEC_NOT_FOUND"
            elif values["SYSTEMD_MAIN_STATUS"] not in ("0", "UNKNOWN"):
                values["SYSTEMD_DIAG_CLASS"] = "MAIN_PROCESS_FAILURE"
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return values



def _bind_preflight_diagnostic(unit, root):
    """Sólo estados seguros del montaje local, sin rutas ni datos remotos."""
    names = _unit_names(root)
    if unit not in names["bind"]:
        return {}
    position = names["bind"].index(unit)
    fuse, binds, _ = _layout(root)
    index, folder, target = binds[position]
    parent = names["fuse"][index]
    data = {
        "BIND_PRE_TARGET_FREE": "UNKNOWN",
        "BIND_PRE_FUSE_MOUNTED": "UNKNOWN",
        "BIND_PRE_SOURCE_DIR": "UNKNOWN",
        "BIND_PARENT_ACTIVE": "UNKNOWN",
        "BIND_PARENT_RESULT": "UNKNOWN",
        "BIND_PRE_LIKELY_STEP": "UNDETERMINED",
    }
    try:
        mounts = _mount_records(_read_mountinfo())
        target_free = target not in mounts
        fuse_present = any(
            entry["fstype"] == "fuse.rclone"
            for entry in mounts.get(fuse[index], ()))
        data["BIND_PRE_TARGET_FREE"] = "YES" if target_free else "NO"
        data["BIND_PRE_FUSE_MOUNTED"] = "YES" if fuse_present else "NO"
        # Evitar acceso al FUSE si no aparece realmente en mountinfo.
        if fuse_present:
            data["BIND_PRE_SOURCE_DIR"] = (
                "YES" if os.path.isdir(fuse[index] + "/" + folder)
                else "NO")
        if not target_free:
            data["BIND_PRE_LIKELY_STEP"] = "TARGET_ALREADY_MOUNTED"
        elif not fuse_present:
            data["BIND_PRE_LIKELY_STEP"] = "FUSE_NOT_MOUNTED"
        elif data["BIND_PRE_SOURCE_DIR"] == "NO":
            data["BIND_PRE_LIKELY_STEP"] = "SOURCE_DIR_NOT_READY"
        elif data["BIND_PRE_SOURCE_DIR"] == "YES":
            data["BIND_PRE_LIKELY_STEP"] = "CHECK_PASSED_AT_DIAG_TIME"
    except (OSError, ValueError, UnicodeError):
        pass
    try:
        ok, raw = _run([
            "systemctl", "show", parent, "--no-pager",
            "--property=ActiveState", "--property=Result"
        ], timeout=9, output=True)
        if ok and isinstance(raw, bytes) and len(raw) < 4096:
            for line in raw.decode("utf-8", "replace").splitlines():
                key, sep, value = line.partition("=")
                if not sep or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value):
                    continue
                if key == "ActiveState":
                    data["BIND_PARENT_ACTIVE"] = value
                elif key == "Result":
                    data["BIND_PARENT_RESULT"] = value
    except (OSError, ValueError, subprocess.SubprocessError):
        pass
    return data


def _emit_service_diagnostic(unit, root):
    data = _service_diagnostic(unit, root)
    data.update(_bind_preflight_diagnostic(unit, root))
    # Evitar que un fallo de inspección impida limpiar recursos temporales.
    for name, value in data.items():
        print(name + "=" + value)


def _read_sample(path):
    try:
        p = subprocess.run(
            [sys.executable, "-c",
             "import sys; f=open(sys.argv[1],'rb'); "
             "sys.exit(0 if f.read()=="
             + repr(SAMPLE) + " else 1)",
             path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL, timeout=12, check=False,
            env=_clean_env())
        return p.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _create_root():
    if os.path.realpath(TMP) != TMP:
        raise ValueError("Unexpected tmp root")
    for _ in range(5):
        root = Path(TMP) / (PREFIX + secrets.token_hex(8))
        try:
            root.mkdir(mode=0o700)
            return root
        except FileExistsError:
            pass
    raise ValueError("Cannot allocate unique lab directory")


def _prepare_dirs(root):
    fuse, binds, fixtures = _layout(root)
    for source in fixtures:
        for folder in ("movies", "tvshows"):
            dest = source / folder
            dest.mkdir(parents=True, mode=0o700)
            (dest / "sample.bin").write_bytes(SAMPLE)
    for path in fuse + [target for _, _, target in binds]:
        Path(path).mkdir(parents=True, mode=0o700)


def _write_units(units):
    created = []
    for name, data in units.items():
        target = os.path.join(RUNTIME_UNITS, name)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(
            os, "O_NOFOLLOW", 0)
        fd = os.open(target, flags, 0o644)
        created.append(name)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return created


def _remove_exact_units(units):
    for name, expected in units.items():
        target = os.path.join(RUNTIME_UNITS, name)
        if not os.path.lexists(target):
            continue
        info = os.lstat(target)
        if not stat.S_ISREG(info.st_mode) or info.st_size != len(expected):
            return False
        with open(target, "rb") as source:
            if source.read(len(expected)+1) != expected:
                return False
    for name in units:
        target = os.path.join(RUNTIME_UNITS, name)
        if os.path.lexists(target):
            os.unlink(target)
    return True


def _cleanup(root, units):
    """Nunca elimina unidades ajenas ni directorios con montajes presentes."""
    names = _unit_names(root)
    safe = True
    # Detener primero bind, luego FUSE. No matar servicios legacy.
    for name in list(reversed(names["bind"])) + list(reversed(names["fuse"])):
        try:
            if not _control("stop", name):
                # Servicios fallidos o no iniciados pueden devolver error.
                if _is_active(name):
                    safe = False
        except (OSError, subprocess.SubprocessError, ValueError):
            safe = False
    try:
        # Si systemd no desmontó un target, solo intentar umount exacto.
        fuse, binds, _ = _layout(root)
        for path in [x[2] for x in reversed(binds)] + list(reversed(fuse)):
            entries = _mount_records(_read_mountinfo())
            if path in entries:
                ok, _ = _run([shutil.which("umount") or "/bin/umount",
                              path], timeout=12)
                if not ok:
                    safe = False
        if _any_lab_mounted(root):
            safe = False
        if any(_is_active(n) for n in names["bind"] + names["fuse"]):
            safe = False
    except (OSError, ValueError, subprocess.SubprocessError):
        safe = False
    if not safe:
        return False
    try:
        if not _remove_exact_units(units):
            return False
        if not _control("daemon-reload"):
            return False
        for name in names["bind"] + names["fuse"]:
            _control("reset-failed", name)
        if _any_lab_mounted(root):
            return False
        shutil.rmtree(root)
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def run_isolated():
    requirements = prerequisites()
    if not all(requirements.values()):
        return "BLOCKED_MISSING_PREREQUISITE"
    try:
        root = _create_root()
    except (OSError, ValueError):
        return "FAIL_CANNOT_ALLOCATE_ISOLATED_TMP"
    names = _unit_names(root)
    units = {}
    status = "FAIL_ISOLATED_SYSTEMD"
    try:
        _prepare_dirs(root)
        units = _unit_files(
            root, rclone_binary(),
            mount_cmd=shutil.which("mount"),
            umount_cmd=shutil.which("umount"),
            mountpoint_cmd=shutil.which("mountpoint"))
        if _any_lab_mounted(root):
            status = "BLOCKED_UNEXPECTED_LAB_MOUNT"
        else:
            _write_units(units)
            if not _control("daemon-reload"):
                status = "FAIL_RUNTIME_RELOAD"
            else:
                for name in names["fuse"] + names["bind"]:
                    if not _control("start", name):
                        _emit_service_diagnostic(name, root)
                        status = "FAIL_SERVICE_START"
                        break
                else:
                    try:
                        if (not all(_is_active(n) for n in
                                    names["fuse"] + names["bind"])
                                or not _check_mounts(_read_mountinfo(), root)):
                            status = "FAIL_SYSTEMD_MOUNT_LAYOUT"
                        else:
                            _, binds, _ = _layout(root)
                            if all(_read_sample(os.path.join(dest, "sample.bin"))
                                   for _, _, dest in binds):
                                status = "PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL"
                            else:
                                status = "FAIL_LOCAL_SAMPLE_READ"
                    except (OSError, ValueError, UnicodeError):
                        status = "FAIL_SYSTEMD_HEALTH"
    except (OSError, ValueError, subprocess.SubprocessError):
        status = "FAIL_SYSTEMD_RUNTIME"
    finally:
        try:
            clean = _cleanup(root, units)
        except (OSError, ValueError, subprocess.SubprocessError):
            clean = False
    if not clean:
        print("CLEANUP=INCOMPLETE_REVIEW_MANUALLY")
        print("LAB_TEMP_ROOT=" + str(root))
        print("LAB_UNIT_PREFIX=" + _identity(root))
        return "FAIL_SYSTEMD_CLEANUP"
    print("CLEANUP=COMPLETE")
    return status


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if args not in (
            ["--preflight"],
            ["--run-isolated-systemd", "--confirm-isolated-only"]):
        print("LAB_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=RCLONE_2FUSE_4BIND_REAL_SYSTEMD_ISOLATED")
    print("ONEDRIVE_ACCESSED=NO")
    print("LIVE_RCLONE_CONFIG_READ=NO")
    print("KODI_MOUNT_PATHS_CHANGED=NO")
    print("LEGACY_SERVICE_START_STOP=NO")
    print("LEGACY_UNIT_FILES_CHANGED=NO")
    print("SYSTEMD_DAEMON_RELOAD=ISOLATED_RUN_ONLY")
    print("SYSTEMD_RUNTIME_UNITS_ONLY=YES")
    print("PERMANENT_UNITS_ENABLED=NO")
    print("GITHUB_UPLOAD=NO")
    if args == ["--preflight"]:
        values = prerequisites()
        for key in sorted(values):
            print(key.upper() + "=" + ("YES" if values[key] else "NO"))
        allowed = all(values.values())
        print("LAB_RESULT=" + ("READY_FOR_ISOLATED_SYSTEMD"
                               if allowed else "BLOCKED_MISSING_PREREQUISITE"))
        return 0 if allowed else 2
    result = run_isolated()
    print("LAB_RESULT=" + result)
    return 0 if result == "PASS_REAL_SYSTEMD_2FUSE_4BIND_LOCAL" else 2


if __name__ == "__main__":
    sys.exit(main())
