# -*- coding: utf-8 -*-
"""Piloto de OAuth de solo lectura: MASTER y CLIENTE simulado.

No publica en GitHub, no reemplaza el rclone.conf real.
Solo crea copias temporales privadas en /tmp para simular un token roto.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "lib" / "rclone_token_policy.py").is_file():
    ROOT = Path("/storage/.kodi/addons/service.cloud.masqelec")
if not (ROOT / "lib" / "rclone_token_policy.py").is_file():
    raise SystemExit("PILOT_ERROR=addon_modules_unavailable")
sys.path.insert(0, str(ROOT))
from lib import chacha_pure, constants, rclone_conf_merge, rclone_token_policy

LOCAL_CONF = "/storage/.config/rclone/rclone.conf"
AUTHORIZED_KEYS = "/storage/.ssh/authorized_keys"
MAX_CONF = 1024 * 1024


def _key_from_file(path):
    with open(path, "rb") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith(b"#"):
                return hashlib.sha256(line).digest()
    raise ValueError("No se encontró la clave configurada")


def _read(path):
    if os.path.islink(path):
        raise ValueError("rclone.conf es enlace simbólico")
    with open(path, "rb") as handle:
        raw = handle.read(MAX_CONF + 1)
    if not raw or len(raw) > MAX_CONF:
        raise ValueError("Configuración local vacía o demasiado grande")
    return raw


def _published(key):
    if constants.CLOUD_BRANCH != "develop":
        raise ValueError("Ensayo permitido únicamente en develop")
    url = (constants.CLOUD_RAW_BASE.rstrip("/") +
           "/rclone/rclone.conf.crypt?oauth_pilot=" + str(int(time.time())))
    req = urllib.request.Request(url, headers={
        "User-Agent": "masQelec-oauth-pilot/1.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=25) as response:
        payload = response.read(2 * MAX_CONF + 1)
    if not payload or len(payload) > 2 * MAX_CONF:
        raise ValueError("Descarga cifrada inválida")
    raw = chacha_pure.decrypt_v2(payload, key)
    if not raw or len(raw) > MAX_CONF:
        raise ValueError("Descifrado produjo una configuración inválida")
    rclone_token_policy.sections(raw)
    rclone_token_policy.oauth_tokens(raw)
    return raw


def _invalidate_for_test(raw, target):
    """Altera únicamente los bytes de una copia temporal de la configuración."""
    found, current, lines = False, None, []
    for line in rclone_conf_merge._lines(raw):
        sec = rclone_conf_merge._SECTION.match(line)
        if sec:
            current = sec.group(1)
        opt = rclone_conf_merge._OPTION.match(line)
        if current == target and opt and opt.group(1).lower() == "token":
            token = json.loads(opt.group(2))
            token["refresh_token"] = "invalid-test-refresh-token-nonexistent"
            token["access_token"] = "invalid-test-access-token"
            token["expiry"] = "2000-01-01T00:00:00Z"
            line = line[:line.index("=") + 1] + " " + json.dumps(
                token, separators=(",", ":"))
            found = True
        lines.append(line)
    if not found:
        raise ValueError("Remoto de prueba sin token OAuth")
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def _rclone():
    for path in ("/storage/.config/rclone/rclone", "/storage/.opt/bin/rclone",
                 "/usr/bin/rclone", "/usr/local/bin/rclone"):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    binary = shutil.which("rclone")
    if binary:
        return binary
    raise FileNotFoundError("rclone no disponible")


def _probe(binary, name, config_path):
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        return "UNKNOWN"
    cmd = [binary, "lsf", name + ":", "--max-depth=1", "--config", config_path,
           "--retries=1", "--low-level-retries=1",
           "--contimeout=10s", "--timeout=20s"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return "UNKNOWN"
    if result.returncode == 0:
        return "OK"
    return ("AUTH" if rclone_token_policy.auth_failure(result.stderr[-8192:])
            else "UNKNOWN")


def _private_file(folder, name, raw):
    path = os.path.join(folder, name)
    with open(path, "xb") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
    return path


def _master_check(local, remote):
    try:
        changed = rclone_token_policy.master_should_publish(local, remote)
    except ValueError:
        print("MASTER_PUBLISH_DECISION=REVIEW_REQUIRED")
    else:
        print("MASTER_PUBLISH_DECISION=" +
              ("CHANGED" if changed else "UNCHANGED"))


def _client_simulation(remote):
    names = sorted(rclone_token_policy.oauth_tokens(remote))
    if not names:
        print("SIMULATION=NO_GOOGLE_DRIVE_TOKEN")
        return 2
    binary = _rclone()
    with tempfile.TemporaryDirectory(prefix="masqelec-oauth-pilot-", dir="/tmp") as temp:
        os.chmod(temp, 0o700)
        # Cliente simulado: sólo el primer remoto Google Drive.
        broken = _invalidate_for_test(remote, names[0])
        candidate = rclone_token_policy.tokens_from_master(broken, remote, [names[0]])
        bad_path = _private_file(temp, "invalid.conf", broken)
        good_path = _private_file(temp, "candidate.conf", candidate)
        before = _probe(binary, names[0], bad_path)
        after = _probe(binary, names[0], good_path)
        print("SIMULATED_BROKEN_TOKEN=" + before)
        print("SIMULATED_RECOVERY=" + after)
        if before == "AUTH" and after == "OK":
            print("SIMULATION=PASS")
            return 0
        print("SIMULATION=INCONCLUSIVE")
        return 2


def main():
    parser = argparse.ArgumentParser(
        description="Prueba OAuth sin alterar configuración real")
    parser.add_argument("--simulate-client", action="store_true",
                        help="simula un cliente roto usando exclusivamente /tmp")
    parser.add_argument("--config", default=LOCAL_CONF)
    parser.add_argument("--key-file", default=AUTHORIZED_KEYS)
    opts = parser.parse_args()

    print("BRANCH=" + constants.CLOUD_BRANCH)
    print("WRITE_LIVE_CONFIG=NO")
    print("GITHUB_UPLOAD=NO")
    local = _read(opts.config)
    remote = _published(_key_from_file(opts.key_file))
    print("MQC2_DECRYPT=PASS")
    print("LOCAL_GOOGLE_DRIVE_REMOTES=" +
          str(len(rclone_token_policy.oauth_tokens(local))))
    print("PUBLISHED_GOOGLE_DRIVE_REMOTES=" +
          str(len(rclone_token_policy.oauth_tokens(remote))))
    _master_check(local, remote)
    if opts.simulate_client:
        return _client_simulation(remote)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Evitar traceback: no se muestran valores ni líneas de credenciales.
        print("PILOT_ERROR=" + type(error).__name__)
        sys.exit(1)
