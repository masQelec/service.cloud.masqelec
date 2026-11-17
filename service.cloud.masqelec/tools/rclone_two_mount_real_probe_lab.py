# -*- coding: utf-8 -*-
"""Sondeo real aislado de los dos OneDrive + MQC2 en GitHub: SOLO LECTURA.

NO INSTALA ni cambia unidades; no publica en GitHub ni toca los mounts.
Un lsf real puede RENOVAR un refresh_token, pero sólo en una COPIA PRIVADA.
No registra nombres de remotos, claves, stderr de rclone ni OAuth.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

SOURCE_REF = "636866996cd72551ef37eb4439c6f023d5c3561d"
SOURCE = ("https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/"
          + SOURCE_REF + "/service.cloud.masqelec/lib/")
CONTENTS_URL = (
    "https://api.github.com/repos/masQelec/cloud.masqelec/"
    "contents/rclone/rclone.conf.crypt?ref=develop"
)
BRANCH_URL = "https://api.github.com/repos/masQelec/cloud.masqelec/branches/develop"
LIVE_CONFIG = "/storage/.config/rclone/rclone.conf"
AUTH_KEYS = "/storage/.ssh/authorized_keys"
STAGE = "BOOT"


def fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "masQelec-oauth-v2-real-probe/1.0",
        "Accept": "application/vnd.github+json",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        body = response.read(2 * 1024 * 1024 + 1)
    if len(body) < 1 or len(body) > 2 * 1024 * 1024:
        raise ValueError("Respuesta de red fuera de límite")
    return body


def github_branch_head():
    """HEAD de cloud/develop: fence adicional frente a blob SHA tipo ABA."""
    response = json.loads(fetch(BRANCH_URL))
    try:
        sha = response["commit"]["sha"]
    except (TypeError, KeyError):
        raise ValueError("HEAD remoto de GitHub inválido")
    if not isinstance(sha, str) or len(sha) != 40 or any(
            c not in "0123456789abcdef" for c in sha):
        raise ValueError("SHA de commit remoto inválido")
    return sha


def read_live_stable():
    if os.path.islink(LIVE_CONFIG):
        raise ValueError("Configuración operativa en symlink")
    before = os.stat(LIVE_CONFIG)
    if not 0 < before.st_size <= 1024 * 1024:
        raise ValueError("Tamaño de configuración operativa anómalo")
    with open(LIVE_CONFIG, "rb") as fd:
        raw = fd.read(1024 * 1024 + 1)
    after = os.stat(LIVE_CONFIG)
    if (len(raw) != before.st_size or
            (before.st_dev, before.st_ino, before.st_size,
             before.st_ctime_ns, before.st_mtime_ns) !=
            (after.st_dev, after.st_ino, after.st_size,
             after.st_ctime_ns, after.st_mtime_ns)):
        raise RuntimeError("La configuración cambió durante lectura")
    return raw


def read_key():
    with open(AUTH_KEYS, "rb") as stream:
        for raw in stream:
            stripped = raw.strip()
            if stripped and not stripped.startswith(b"#"):
                return hashlib.sha256(stripped).digest()
    raise ValueError("Clave del dispositivo no disponible")


def which_rclone():
    for binary in (
        "/storage/.config/rclone/rclone", "/storage/.opt/bin/rclone",
        "/usr/bin/rclone", "/usr/local/bin/rclone",
    ):
        if os.path.isfile(binary) and os.access(binary, os.X_OK):
            return binary
    found = shutil.which("rclone")
    if not found:
        raise ValueError("Rclone ejecutable no encontrado")
    return os.path.realpath(found)


def any_rclone_mounts_alive():
    """Bloqueo antes de probar OAuth: rclone podría rotar el refresh remoto.

    No basta que el fichero --config sea una copia privada. Si Microsoft
    invalida otro refresh token, un mount vivo puede quedarse sin acceso.
    Sin /proc completo o permisos suficientes se falla de forma segura.
    """
    try:
        processes = os.scandir("/proc")
    except OSError:
        return True
    try:
        for entry in processes:
            if not entry.name.isdecimal() or int(entry.name) == os.getpid():
                continue
            try:
                with open(entry.path + "/cmdline", "rb") as f:
                    raw_cmdline = f.read(16385)
                    if len(raw_cmdline) > 16384:
                        return True  # Truncamiento: no declarar ausencia de montajes.
                    cmd = [part.decode("utf-8", "replace")
                           for part in raw_cmdline.split(b"\0") if part]
            except (FileNotFoundError, ProcessLookupError):
                continue
            except OSError:
                return True
            if not cmd:
                continue
            if (os.path.basename(cmd[0]).startswith("rclone")
                    and any(arg in ("mount", "mount2", "cmount")
                            for arg in cmd[1:])):
                return True
        return False
    finally:
        processes.close()


def main():
    global STAGE
    mode = "--real-probe" if "--real-probe" in sys.argv[1:] else "--preflight"
    if any(arg not in ("--real-probe", "--preflight") for arg in sys.argv[1:]):
        raise ValueError("Opción no soportada")
    if "--real-probe" in sys.argv[1:] and "--preflight" in sys.argv[1:]:
        raise ValueError("Modos excluyentes")
    print("LAB_MODE=TWO_MOUNT_OAUTH_V2_GITHUB_SHA_AND_PROBE")
    print("CODE_REF=" + SOURCE_REF)
    print("LIVE_CONFIG_WRITE=NO")
    print("MOUNT_RESTART=NO")
    print("SYSTEMD_WRITE=NO")
    print("GITHUB_UPLOAD=NO")
    print("OAUTH_PROBE_REQUESTED=" + ("YES" if mode == "--real-probe" else "NO"))
    if mode == "--real-probe":
        STAGE = "MOUNT_SAFETY_FENCE"
        if any_rclone_mounts_alive():
            print("ACTIVE_RCLONE_MOUNTS=YES_OR_UNKNOWN")
            print("LAB_RESULT=BLOCKED_ACTIVE_MOUNTS")
            return 2
        print("ACTIVE_RCLONE_MOUNTS=NO")
        # No existe aún un protocolo fiable para comprobar escritores en
        # OTROS CLIENTES de la cuenta. El probe puede rotar refresh remoto.
        # Por diseño, se deniega incluso cuando /proc local está vacío.
        STAGE = "FLEET_OAUTH_COORDINATION_FENCE"
        print("FLEET_OAUTH_COORDINATION=NOT_VERIFIED")
        print("LAB_RESULT=BLOCKED_FLEET_COORDINATION")
        return 2

    with tempfile.TemporaryDirectory(
            prefix="masqelec-v2-mqc2-probe-", dir="/tmp") as dirname:
        root = Path(dirname)
        os.chmod(root, 0o700)
        lib = root / "lib"
        lib.mkdir(mode=0o700)
        (lib / "__init__.py").write_bytes(b"")
        names = (
            "rclone_conf_merge.py", "rclone_token_policy.py",
            "rclone_mount_isolation.py", "rclone_two_mount_rollout.py",
            "rclone_two_mount_plan.py", "rclone_two_mount_oauth.py",
            "rclone_two_mount_verify.py",
            "rclone_two_mount_publish_guard.py", "chacha_pure.py",
        )
        for filename in names:
            STAGE = "DOWNLOAD_MODULES"
            destination = lib / filename
            destination.write_bytes(fetch(SOURCE + filename))
            os.chmod(destination, 0o600)
        STAGE = "IMPORT_MODULES"
        sys.path.insert(0, str(root))
        policy = importlib.import_module("lib.rclone_token_policy")
        plan = importlib.import_module("lib.rclone_two_mount_plan")
        coordinator = importlib.import_module("lib.rclone_two_mount_oauth")
        publisher = importlib.import_module("lib.rclone_two_mount_publish_guard")
        verifier = importlib.import_module("lib.rclone_two_mount_verify")

        STAGE = "READ_LIVE_CONFIG"
        canonical = read_live_stable()
        policy.validate_master_layout(canonical)
        print("MASTER_CANONICAL_LAYOUT=PASS")

        STAGE = "READ_DEVICE_KEY"
        key = read_key()
        STAGE = "READ_GITHUB_BRANCH_HEAD"
        branch_head = github_branch_head()
        # Se lee el fichero de la revisión INMUTABLE, no del puntero móvil.
        pinned_url = CONTENTS_URL.replace("?ref=develop", "?ref=" + branch_head)
        STAGE = "READ_AUTHENTICATED_GITHUB_MQC2"
        remote = publisher.decode_remote_contents(fetch(pinned_url), key)
        print("GH_BLOB_SHA_VALID=PASS")
        print("MQC2_AUTHENTICATED=PASS")

        STAGE = "CHECK_STATIC_COMPATIBILITY"
        canonical_options = policy.sections(canonical)
        backup_options = policy.sections(remote["canonical"])
        static_match = all(
            {k: v for k, v in options.items() if k != "token"} ==
            {k: v for k, v in backup_options.get(name, {}).items()
             if k != "token"}
            for name, options in canonical_options.items()
        ) and set(canonical_options) == set(backup_options)
        print("GH_STATIC_IDENTITY=" +
              ("PASS" if static_match else "MISMATCH"))
        if not static_match:
            print("LAB_RESULT=BLOCKED_STATIC_IDENTITY")
            return 2

        STAGE = "CHECK_BASELINE"
        prepared = coordinator.prepare_master(
            canonical,
            (plan.account_snapshot(canonical, 0),
             plan.account_snapshot(canonical, 1)),
            remote["canonical"],
        )
        if prepared["status"] == "published_baseline_diverged":
            print("GH_OAUTH_BASELINE=DIFFERENT")
            print("LAB_RESULT=BLOCKED_BASELINE_DIVERGED")
            return 2
        if prepared["status"] != "unchanged":
            raise ValueError("Sin rotación no puede prepararse publicación")
        print("GH_OAUTH_BASELINE=CONSISTENT")

        STAGE = "STAGE_ACCOUNT_COPIES"
        accounts = (
            plan.account_snapshot(canonical, 0),
            plan.account_snapshot(canonical, 1)
        )
        if len(accounts) != 2:
            raise ValueError("No se prepararon ambas cuentas")
        print("ONE_DRIVE_COPIES_PREPARED=2")

        if mode == "--real-probe":
            STAGE = "FIND_RCLONE_BINARY"
            binary = which_rclone()
            print("RCLONE_BINARY_FOUND=YES")
            for account, raw in enumerate(accounts, 1):
                STAGE = "REAL_PROBE_ACCOUNT_{}".format(account)
                result = verifier.probe_one(canonical, account - 1,
                                            raw, binary)
                state = result["status"]
                print("ACCOUNT_{}_REAL_OAUTH_PROBE={}".format(
                    account, state.upper()))
                if state != "ok":
                    print("LAB_RESULT=BLOCKED_PROBE")
                    return 2
                print("ACCOUNT_{}_TEMP_REFRESH_ROTATED={}".format(
                    account, "YES" if result["refresh_rotated"] else "NO"))
            print("REAL_OAUTH_PROBE=PASS_2_OF_2")
        else:
            print("REAL_OAUTH_PROBE=NOT_EXECUTED")

        STAGE = "RECHECK_LIVE_AND_REMOTE"
        if read_live_stable() != canonical:
            print("LAB_RESULT=INCONCLUSIVE_LOCAL_ROTATED")
            return 2
        second = publisher.decode_remote_contents(fetch(pinned_url), key)
        if second["sha"] != remote["sha"]:
            print("GH_BLOB_SHA_STABLE=NO")
            print("LAB_RESULT=INCONCLUSIVE_GITHUB_UPDATED")
            return 2
        print("GH_BLOB_SHA_STABLE=YES")
        STAGE = "RECHECK_GITHUB_BRANCH_HEAD"
        if github_branch_head() != branch_head:
            print("GH_BRANCH_COMMIT_STABLE=NO")
            print("LAB_RESULT=INCONCLUSIVE_GITHUB_UPDATED")
            return 2
        print("GH_BRANCH_COMMIT_STABLE=YES")
        print("LIVE_CONFIG_CHANGED=NO")
        print("GITHUB_PUBLISH_ALLOWED=NO")
        print("LAB_RESULT=PASS")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("LAB_FAILED_AT=" + STAGE)
        print("LAB_RESULT=ERROR_" + type(exc).__name__)
        sys.exit(1)
