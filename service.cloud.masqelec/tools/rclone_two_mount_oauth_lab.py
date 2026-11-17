# -*- coding: utf-8 -*-
"""Lab de política OAuth v2 con rclone.conf REAL: sin publicar ni recuperar."""
import importlib
import json
import os
from pathlib import Path
import sys
import tempfile
import urllib.request

REF = "6692114279701e78451e78ecf01d7b2ddec86931"
SOURCE = ("https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/"
          + REF + "/service.cloud.masqelec/lib/")
LIVE = "/storage/.config/rclone/rclone.conf"
STAGE = "BOOT"


def download(url):
    request = urllib.request.Request(url, headers={
        "User-Agent": "masQelec-oauth-v2-read-only-lab/1.0",
        "Cache-Control": "no-cache",
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read(256 * 1024 + 1)
    if not data or len(data) > 256 * 1024:
        raise ValueError("Recurso laboratorio inválido")
    return data


def stable_live():
    if os.path.islink(LIVE):
        raise ValueError("Config en vivo es symlink")
    before = os.stat(LIVE)
    if not 0 < before.st_size <= 1024 * 1024:
        raise ValueError("Tamaño de configuración anómalo")
    with open(LIVE, "rb") as reader:
        data = reader.read(1024 * 1024 + 1)
    after = os.stat(LIVE)
    if (len(data) != before.st_size or before.st_size != after.st_size
            or before.st_ino != after.st_ino
            or before.st_mtime_ns != after.st_mtime_ns):
        raise RuntimeError("Escritura concurrente: repetir ensayo")
    return data


def fake_refresh(source, policy, merge):
    """Reemplaza SOLO UN refresh_token EN MEMORIA con marcador inválido.

    El marcador no debe publicarse, probarse contra OneDrive ni escribirse
    en la configuración real. El ensayo comprueba exclusivamente la
    decisión de la política al detectar dos tokens distintos.
    """
    names = tuple(policy.oauth_tokens(source))
    if len(names) != 1:
        raise ValueError("Snapshot debe contener un único OAuth")
    changed = 0
    section = None
    result = []
    for line in merge._lines(source):
        heading = merge._SECTION.match(line)
        if heading:
            section = heading.group(1)
        option = merge._OPTION.match(line)
        if option and option.group(1).lower() == "token" and section == names[0]:
            data = json.loads(option.group(2))
            data["refresh_token"] = "LAB_ONLY_INVALID_NEVER_USE_AS_CREDENTIAL"
            line = line[:line.index("=") + 1] + " " + json.dumps(data)
            changed += 1
        result.append(line)
    if changed != 1:
        raise ValueError("Simulación no modificó exactamente un OAuth")
    return ("\n".join(result).rstrip("\n") + "\n").encode("utf-8")


def run():
    global STAGE
    print("LAB_MODE=TWO_MOUNT_OAUTH_RECONCILIATION_READ_ONLY")
    print("SOURCE_REF=" + REF)
    print("LIVE_CONFIG_WRITE=NO")
    print("MOUNT_RESTART=NO")
    print("SYSTEMD_WRITE=NO")
    print("GITHUB_UPLOAD=NO")
    print("OAUTH_NETWORK_PROBE=NO")
    print("PUBLISHED_MQC2_READ=NO")
    with tempfile.TemporaryDirectory(
            prefix="masqelec-two-mount-oauth-", dir="/tmp") as root:
        os.chmod(root, 0o700)
        lib = Path(root) / "lib"
        lib.mkdir(mode=0o700)
        (lib / "__init__.py").write_bytes(b"")
        for filename in (
                "rclone_conf_merge.py", "rclone_token_policy.py",
                "rclone_mount_isolation.py", "rclone_two_mount_rollout.py",
                "rclone_two_mount_plan.py", "rclone_two_mount_oauth.py"):
            STAGE = "DOWNLOAD_CODE"
            file = lib / filename
            file.write_bytes(download(SOURCE + filename))
            os.chmod(file, 0o600)
        STAGE = "IMPORT"
        sys.path.insert(0, root)
        merge = importlib.import_module("lib.rclone_conf_merge")
        policy = importlib.import_module("lib.rclone_token_policy")
        plan = importlib.import_module("lib.rclone_two_mount_plan")
        coord = importlib.import_module("lib.rclone_two_mount_oauth")
        STAGE = "READ_LIVE"
        canonical = stable_live()
        policy.validate_master_layout(canonical)
        print("CANONICAL_LAYOUT=PASS")
        STAGE = "CREATE_ISOLATED_IN_MEMORY"
        accounts = (plan.account_snapshot(canonical, 0),
                    plan.account_snapshot(canonical, 1))
        if any(len(policy.sections(raw)) != 2
               or len(policy.oauth_tokens(raw)) != 1 for raw in accounts):
            raise ValueError("Cadena crypt/OneDrive no es 2+1")
        print("ISOLATED_CRYPT_ONEDRIVE_CONFIGS=2")
        STAGE = "BASELINE"
        initial = coord.prepare_master(canonical, accounts, canonical)
        if initial["status"] != "unchanged":
            raise ValueError("Sin rotaciones no debe crear candidato")
        print("BASELINE_POLICY=UNCHANGED")
        STAGE = "SIMULATE_UNVERIFIED_ROTATION"
        mutated = fake_refresh(accounts[0], policy, merge)
        prepared = coord.prepare_master(
            canonical, (mutated, accounts[1]), canonical
        )
        if (prepared["status"] != "candidate_requires_probe"
                or len(prepared["changed_names"]) != 1):
            raise ValueError("Rotación ficticia no quedó sin verificar")
        if coord.probe_gate(prepared, {
                prepared["changed_names"][0]: "auth"}) != "probe_failed":
            raise ValueError("El candidato ficticio debe fallar el gate OAuth")
        print("SIMULATED_ROTATION=REQUIRES_REAL_PROBE")
        candidate = prepared["candidate"]
        before, after = policy.sections(canonical), policy.sections(candidate)
        if any(before[name] != after[name]
               for name in before
               if before[name].get("type", "").strip().lower() != "onedrive"):
            raise ValueError("Se cambió crypt o Google Drive")
        print("GOOGLE_DRIVE_AND_CRYPT_PRESERVED=PASS")
        STAGE = "CLIENT_POLICY"
        client = coord.prepare_client(
            canonical, 0, mutated, confirmed_auth_error=True)
        if client["status"] != "candidate_requires_probe_and_safe_apply":
            raise ValueError("Cliente v2 debería exigir sondeo y aplicación segura")
        no_error = coord.prepare_client(canonical, 0, mutated, False)
        if no_error["status"] != "no_explicit_oauth_error":
            raise ValueError("Cliente sin error OAuth no debe recuperar")
        print("CLIENT_SELECTIVE_RECOVERY=PROBE_AND_SAFE_APPLY_REQUIRED")
        STAGE = "CHECK_LIVE_UNMODIFIED"
        if stable_live() != canonical:
            print("LAB_RESULT=INCONCLUSIVE_LIVE_ROTATED")
            return 2
        print("LIVE_CONFIG_CHANGED=NO")
    print("LAB_RESULT=PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        # Nada de valores de excepciones: pudieran contener secretos.
        print("LAB_FAILED_AT=" + STAGE)
        print("LAB_RESULT=ERROR_" + type(exc).__name__)
        sys.exit(1)
