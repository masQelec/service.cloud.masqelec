# -*- coding: utf-8 -*-
"""Laboratorio 2 FUSE + 4 bind, sin tocar rclone ni systemd operativos."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

ADDON_REF = "5cf41965b9a06eea30328cec1717550ef642aca9"
CLOUD_REF = "ffc5ee83a33fdde81ebde120c1fef633077b41c4"
SOURCE = ("https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/"
          + ADDON_REF + "/service.cloud.masqelec/lib/")
CLOUD = ("https://raw.githubusercontent.com/masQelec/cloud.masqelec/"
         + CLOUD_REF + "/")
LIVE = "/storage/.config/rclone/rclone.conf"
PHASE = "BOOT"


def fetch(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "masQelec-two-fuse-lab/1.0",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(256 * 1024 + 1)
    if not data or len(data) > 256 * 1024:
        raise ValueError("Recurso del laboratorio inválido")
    return data


def stable_config():
    if os.path.islink(LIVE):
        raise ValueError("Config real no debe ser enlace simbólico")
    before = os.stat(LIVE)
    if not 0 < before.st_size <= 1024 * 1024:
        raise ValueError("Config real fuera de límite")
    with open(LIVE, "rb") as reader:
        data = reader.read(1024 * 1024 + 1)
    after = os.stat(LIVE)
    if (len(data) != before.st_size or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns
            or before.st_size != after.st_size):
        raise ValueError("Lectura concurrente")
    return data


def lab():
    global PHASE
    print("LAB_MODE=TWO_FUSE_FOUR_BIND_CLIENT_READY")
    print("ADDON_REF=" + ADDON_REF)
    print("CLOUD_REF=" + CLOUD_REF)
    print("LIVE_RCLONE_WRITE=NO")
    print("SYSTEMD_WRITE=NO")
    print("MOUNT_RESTART=NO")
    print("GITHUB_UPLOAD=NO")
    with tempfile.TemporaryDirectory(
            prefix="masqelec-two-fuse-plan-", dir="/tmp") as dirname:
        root = Path(dirname)
        os.chmod(root, 0o700)
        modules = root / "modules"
        lib = modules / "lib"
        lib.mkdir(parents=True, mode=0o700)
        os.chmod(modules, 0o700)
        os.chmod(lib, 0o700)
        (lib / "__init__.py").write_bytes(b"")
        for file in ("rclone_conf_merge.py", "rclone_token_policy.py",
                     "rclone_mount_isolation.py", "rclone_two_mount_rollout.py",
                     "rclone_two_mount_plan.py"):
            PHASE = "DOWNLOAD_CODE"
            dest = lib / file
            dest.write_bytes(fetch(SOURCE + file))
            os.chmod(dest, 0o600)
        PHASE = "IMPORT"
        sys.path.insert(0, str(modules))
        plan = importlib.import_module("lib.rclone_two_mount_plan")
        rollout = importlib.import_module("lib.rclone_two_mount_rollout")
        PHASE = "READ_LIVE"
        original = stable_config()
        PHASE = "GET_CURRENT_UNITS"
        units = {name: fetch(CLOUD + "system.d/" + name)
                 for name, _, _, _ in plan.isolation.MOUNT_SPECS}
        plan.validate_legacy_units(units)
        print("LEGACY_UNITS_VALID=PASS")
        PHASE = "MANIFEST"
        manifest = json.loads(fetch(
            CLOUD + "rollouts/rclone-two-mount/v1/manifest.json"))
        if (not rollout.version_supported(manifest)
                or manifest.get("auto_apply") is not False
                or manifest.get("production_authorized") is not False):
            raise ValueError("Manifiesto sin barreras de despliegue")
        print("REMOTE_MANIFEST=STAGE_ONLY")
        print("PRODUCTION_AUTHORIZED=NO")
        PHASE = "STAGE_PLAN"
        proposal = root / "proposal"
        proposal.mkdir(mode=0o700)
        summary = plan.stage_to_tmp(str(proposal), original, units)
        PHASE = "VERIFY_STAGE"
        if not rollout.version_supported(summary):
            raise ValueError("Manifiesto local incompatible")
        items = list(proposal.iterdir())
        if len(items) != 9:
            raise ValueError("Número inesperado de borradores")
        for item in items:
            mode = 0o600 if (item.suffix == ".conf"
                             or item.name == "rollout-manifest.json") else 0o644
            if os.stat(item).st_mode & 0o777 != mode:
                raise ValueError("Permisos de archivo preparado incorrectos")
        print("STAGED_SECRET_CONFIGS=2")
        print("STAGED_FUSE_SERVICES=2")
        print("STAGED_BIND_SERVICES=4")
        print("KODI_COMPAT_PATHS=4")
        print("PRIVATE_CONFIG_PERMISSIONS=0600")
        print("STAGED_SYSTEMD_UNITS=NOT_INSTALLED")
        print("TYPE_NOTIFY_REAL_VERIFIED=NO")
        print("OAUTH_V2_RECONCILIATION_ENABLED=NO")
        PHASE = "VERIFY_LIVE"
        if stable_config() != original:
            raise ValueError("rclone.conf cambió durante el laboratorio")
        print("LIVE_CONFIG_CHANGED=NO")
    print("LAB_RESULT=PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(lab())
    except Exception as exc:
        print("LAB_FAILED_AT=" + PHASE)
        print("LAB_RESULT=ERROR_" + type(exc).__name__)
        sys.exit(1)
