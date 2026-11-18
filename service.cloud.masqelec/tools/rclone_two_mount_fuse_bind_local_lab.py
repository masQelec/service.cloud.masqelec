# -*- coding: utf-8 -*-
"""Piloto de 2 rclone FUSE + 4 bind usando SOLO ficheros locales ficticios.

--preflight: solo consulta disponibilidad de binarios y /dev/fuse.
--run-local-pilot --confirm-isolated-only: crea una raíz temporal 0700 bajo
/tmp, monta 2 rclone del backend LOCAL usando --config /dev/null, hace
4 bind dentro de la MISMA raíz, verifica lectura / mountinfo y desmonta.
NUNCA abre rclone.conf, claves, OneDrive, carpetas Kodi o system.d.
No acredita Type=notify en systemd ni descifrado crypt real.
"""
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

# Autocontenido: puede descargarse a /tmp y ejecutarse por SSH sin
# instalar una nueva versión del addon en KodiELEC.
def _mount_entries(data):
    """Parseo mínimo de /proc/self/mountinfo; solo datos de montajes."""
    entries = {}
    for line in data.splitlines():
        left, sep, right = line.partition(" - ")
        a, b = left.split(), right.split()
        if not sep or len(a) < 6 or len(b) < 3:
            raise ValueError("mountinfo inválido")
        entries[a[4]] = {
            "device": a[2], "fsroot": a[3],
            "fstype": b[0], "source": b[1],
        }
    return entries


def _check_alternate_layout(data, fuse, binds):
    try:
        entries = _mount_entries(data)
    except (ValueError, TypeError):
        return False
    for index, folder, target in binds:
        root, child = entries.get(fuse[index]), entries.get(target)
        if root is None or child is None or root["fstype"] != "fuse.rclone":
            return False
        expected = root["fsroot"].rstrip("/") + "/" + folder
        if child["fsroot"] != expected:
            return False
        if any(child[key] != root[key] for key in (
                "device", "fstype", "source")):
            return False
    return True

# Ninguna ruta real /storage es válida como destino en este laboratorio.
_TEMP_ROOT = "/tmp"
_SAMPLE = b"masQelec-local-pilot-placeholder\n"


def rclone_binary():
    """El binario KodiELEC suele vivir fuera de PATH; no ejecuta nada."""
    for path in (
            "/storage/.config/rclone/rclone", "/usr/bin/rclone",
            "/usr/local/bin/rclone"):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return shutil.which("rclone")


def _rclone_mount_flags_supported(executable):
    """Consulta ayuda local del binario, sin llamar a ningún backend."""
    if not executable:
        return False
    try:
        help_text = subprocess.run(
            [executable, "mount", "--help"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=12,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if help_text.returncode:
        return False
    return all(flag in help_text.stdout for flag in (
        b"--read-only", b"--vfs-cache-mode", b"--config"))


def prerequisites():
    """Solo estructura, sin dar por probado Type=notify ni un montaje."""
    binary = rclone_binary()
    try:
        fuse = (os.path.exists("/dev/fuse") and
                stat.S_ISCHR(os.stat("/dev/fuse").st_mode))
    except OSError:
        fuse = False
    return {
        "rclone": binary is not None,
        "rclone_mount_flags": _rclone_mount_flags_supported(binary),
        "mount": shutil.which("mount") is not None,
        "umount": shutil.which("umount") is not None,
        "fuse_device": fuse,
        "mountinfo": os.path.isfile("/proc/self/mountinfo"),
        "privileged": os.geteuid() == 0,
    }


def layout(root):
    """Cuatro destinos de ensayo completamente fuera de /storage."""
    root = Path(root)
    if (root.parent != Path(_TEMP_ROOT) or root.is_symlink()
            or not root.name.startswith("masqelec-fuse-local-")):
        raise ValueError("Raíz fuera del laboratorio")
    fuse = tuple(str(root / "fuse" / str(i)) for i in (1, 2))
    binds = tuple(
        (i - 1, folder, str(root / "bind" / group / str(i)))
        for group, folder in (("videos", "movies"), ("tvshows", "tvshows"))
        for i in (1, 2)
    )
    sources = tuple(root / "fixtures" / str(i) for i in (1, 2))
    return fuse, binds, sources


def _mountinfo():
    with open("/proc/self/mountinfo", "r", encoding="utf-8") as f:
        return f.read()


def _is_mounted(path):
    return path in _mount_entries(_mountinfo())


def _wait_for_fuse(proc, target, seconds=12):
    for _ in range(seconds * 10):
        if proc.poll() is not None:
            return False
        try:
            entry = health.mount_entries(_mountinfo()).get(target)
        except (ValueError, OSError):
            entry = None
        if entry is not None and entry["fstype"] == "fuse.rclone":
            return True
        time.sleep(0.1)
    return False


def _run(command):
    subprocess.run(command, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL, timeout=12, check=True)


def _safe_environment():
    """Ignora opciones de rclone y credenciales heredadas por accidente."""
    return {
        k: v for k, v in os.environ.items()
        if not k.startswith(("RCLONE_", "AWS_", "AZURE_",
                             "GOOGLE_", "ONEDRIVE_"))
    }


def _cleanup(root, binds, fuse, processes):
    """Solo trata montajes de la raíz aleatoria del laboratorio."""
    all_unmounted = True
    for _, _, target in reversed(binds):
        try:
            if _is_mounted(target):
                _run(["umount", target])
        except (OSError, ValueError, subprocess.SubprocessError):
            all_unmounted = False
    for target in reversed(fuse):
        try:
            if _is_mounted(target):
                _run(["umount", target])
        except (OSError, ValueError, subprocess.SubprocessError):
            all_unmounted = False
    for proc in reversed(processes):
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    all_unmounted = False
    for target in list(fuse) + [x[2] for x in binds]:
        try:
            if _is_mounted(target):
                all_unmounted = False
        except (OSError, ValueError):
            all_unmounted = False
    if all_unmounted:
        try:
            shutil.rmtree(root)
        except OSError:
            all_unmounted = False
    return all_unmounted


class _PilotStop(Exception):
    def __init__(self, status):
        self.status = status


def run_local_pilot():
    """PASS solo tras confirmar además desmontaje y limpieza completos."""
    required = prerequisites()
    if not all(required.values()):
        return "BLOCKED_MISSING_LOCAL_PREREQUISITE"
    if os.path.realpath("/tmp") != "/tmp":
        return "BLOCKED_UNSAFE_TMP_ROOT"

    root = Path(tempfile.mkdtemp(prefix="masqelec-fuse-local-", dir=_TEMP_ROOT))
    fuse, binds, sources = layout(root)
    processes = []
    result = "FAIL_LOCAL_PILOT"
    try:
        for src in sources:
            for folder in ("movies", "tvshows"):
                target = src / folder
                target.mkdir(parents=True, exist_ok=True)
                (target / "sample.bin").write_bytes(_SAMPLE)
        for point in fuse:
            os.makedirs(point, mode=0o700)
        for _, _, target in binds:
            os.makedirs(target, mode=0o700)

        for src, point in zip(sources, fuse):
            proc = subprocess.Popen(
                [rclone_binary(), "mount", str(src), point,
                 "--config", "/dev/null", "--read-only",
                 "--vfs-cache-mode", "off"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL, start_new_session=True,
                env=_safe_environment(),
            )
            processes.append(proc)
            if not _wait_for_fuse(proc, point):
                raise _PilotStop("FAIL_LOCAL_FUSE_NOT_READY")

        for index, folder, target in binds:
            source_path = str(Path(fuse[index]) / folder)
            _run(["mount", "--bind", source_path, target])

        if not _check_alternate_layout(_mountinfo(), fuse, binds):
            raise _PilotStop("FAIL_LOCAL_MOUNTINFO_LAYOUT")

        for _, _, target in binds:
            with open(os.path.join(target, "sample.bin"), "rb") as f:
                if f.read(1024) != _SAMPLE:
                    raise _PilotStop("FAIL_LOCAL_READ_MISMATCH")
        result = "PASS_LOCAL_FUSE_BIND_LAB"
    except _PilotStop as exc:
        result = exc.status
    except (OSError, ValueError, subprocess.SubprocessError):
        result = "FAIL_LOCAL_RUNTIME"
    finally:
        # No borrar directorios donde aún puede existir un FUSE o bind.
        cleaned = _cleanup(root, binds, fuse, processes)
    if not cleaned:
        print("CLEANUP=INCOMPLETE_TEMP_PATH_REQUIRES_MANUAL_REVIEW")
        return "FAIL_LOCAL_CLEANUP"
    return result


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv not in (["--preflight"],
                    ["--run-local-pilot", "--confirm-isolated-only"]):
        print("LAB_RESULT=BLOCKED_INVALID_MODE")
        return 2
    print("LAB_MODE=RCLONE_TWO_FUSE_FOUR_BIND_LOCAL")
    print("ONEDRIVE_ACCESSED=NO")
    print("RCLONE_LIVE_CONFIG_READ=NO")
    print("KODI_PATHS_CHANGED=NO")
    print("SYSTEMD_WRITE=NO")
    print("GITHUB_UPLOAD=NO")
    if argv == ["--preflight"]:
        info = prerequisites()
        for key in sorted(info):
            print(key.upper() + "=" + ("YES" if info[key] else "NO"))
        print("TYPE_NOTIFY_REAL_SYSTEMD=NOT_TESTED")
        print("LAB_RESULT=READY_FOR_LOCAL_PILOT" if all(info.values())
              else "LAB_RESULT=BLOCKED_MISSING_LOCAL_PREREQUISITE")
        return 0 if all(info.values()) else 2
    result = run_local_pilot()
    print("LAB_RESULT=" + result)
    return 0 if result == "PASS_LOCAL_FUSE_BIND_LAB" else 2


if __name__ == "__main__":
    sys.exit(main())
