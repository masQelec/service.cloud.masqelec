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


def _classify_failure(stderr):
    """Clasifica sin registrar el stderr: algunas URLs contienen credenciales."""
    if isinstance(stderr, bytes):
        value = stderr[-8192:].decode("utf-8", "replace").lower()
    else:
        value = str(stderr or "")[-8192:].lower()
    if rclone_token_policy.auth_failure(value):
        return "AUTH"
    if any(word in value for word in (
        "invalid_grant", "invalid_token", "401 unauthorized", "oauth2",
        "couldn't fetch token", "token expired", "token has expired",
    )):
        # El detalle exacto se revisará en el motor; no conceder acceso.
        return "OAUTH_SUSPECT"
    if any(word in value for word in (
        "rate limit", "too many requests", "429", "ratelimitexceeded",
    )):
        return "RATE_LIMIT"
    if "quota" in value:
        return "QUOTA"
    if any(word in value for word in (
        "403", "forbidden", "insufficientpermissions",
        "permission denied", "access denied",
    )):
        return "PERMISSION"
    if any(word in value for word in (
        "couldn't find root directory", "directory not found",
        "path not found", "object not found", "file not found",
        "404 not found",
    )):
        return "REMOTE_PATH"
    if any(word in value for word in (
        "didn't find section", "failed to load config",
        "failed to parse config", "invalid configuration",
        "failed to create file system for",
    )):
        return "RCLONE_CONFIG"
    if any(word in value for word in (
        "x509", "tls handshake", "certificate verify",
    )):
        return "TLS"
    if any(word in value for word in (
        "timeout", "connection", "no such host", "network is unreachable",
        "no route to host", "temporary failure in name resolution",
        "i/o timeout", "lookup ",
    )):
        return "NETWORK"
    return "UNCLASSIFIED"


def _probe_details(binary, name, config_path):
    """(estado, causa, salida). No muestra ni conserva stderr sin filtrar."""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        return ("UNKNOWN", "INVALID_REMOTE_NAME", None)
    cmd = [binary, "lsf", name + ":", "--max-depth=1", "--config", config_path,
           "--retries=1", "--low-level-retries=1",
           "--contimeout=10s", "--timeout=20s"]
    try:
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, timeout=45, check=False)
    except subprocess.TimeoutExpired:
        return ("UNKNOWN", "PROCESS_TIMEOUT", None)
    except OSError:
        return ("UNKNOWN", "EXEC_FAILURE", None)
    if result.returncode == 0:
        return ("OK", "OK", 0)
    reason = _classify_failure(result.stderr)
    return ("AUTH" if reason == "AUTH" else "UNKNOWN", reason,
            result.returncode)


def _probe(binary, name, config_path):
    """Interfaz anterior para pruebas existentes."""
    return _probe_details(binary, name, config_path)[0]


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


def _client_simulation(remote, local=None, remote_index=1):
    supported = rclone_token_policy.oauth_tokens(remote)
    options = rclone_token_policy.sections(remote)
    # OneDrive primero: biblioteca multimedia prioritaria; nombres no se imprimen.
    names = sorted(supported, key=lambda name: (
        0 if options[name].get("type", "").strip().lower() == "onedrive" else 1,
        name,
    ))
    if not names:
        print("SIMULATION=NO_OAUTH_TOKEN")
        return 2
    if remote_index < 1 or remote_index > len(names):
        print("SIMULATION=INVALID_REMOTE_INDEX")
        print("AVAILABLE_OAUTH_REMOTES=" + str(len(names)))
        return 2
    name = names[remote_index - 1]
    print("TARGET_REMOTE_INDEX=" + str(remote_index))
    print("TARGET_REMOTE_PROVIDER=" + options[name].get("type", "").strip().lower())
    binary = _rclone()
    with tempfile.TemporaryDirectory(prefix="masqelec-oauth-pilot-", dir="/tmp") as temp:
        os.chmod(temp, 0o700)
        broken = _invalidate_for_test(remote, name)
        candidate = rclone_token_policy.tokens_from_master(broken, remote, [name])
        bad_path = _private_file(temp, "invalid.conf", broken)
        good_path = _private_file(temp, "candidate.conf", candidate)
        before, before_reason, before_rc = _probe_details(binary, name, bad_path)
        after, after_reason, after_rc = _probe_details(binary, name, good_path)
        print("SIMULATED_BROKEN_TOKEN=" + before)
        print("SIMULATED_BROKEN_REASON=" + before_reason)
        print("SIMULATED_RECOVERY=" + after)
        print("SIMULATED_RECOVERY_REASON=" + after_reason)
        print("SIMULATED_RECOVERY_EXIT=" + str(after_rc))
        if before == "AUTH" and after == "OK":
            print("SIMULATION=PASS")
            return 0

        if after != "OK" and local is not None:
            # Copia privada del local para determinar si también falla el
            # acceso normal. NUNCA se pasa la ruta del rclone.conf activo.
            local_names = rclone_token_policy.oauth_tokens(local)
            if name in local_names:
                local_path = _private_file(temp, "local-copy.conf", local)
                baseline, baseline_reason, baseline_rc = _probe_details(
                    binary, name, local_path)
                print("LOCAL_COPY_BASELINE=" + baseline)
                print("LOCAL_COPY_BASELINE_REASON=" + baseline_reason)
                print("LOCAL_COPY_BASELINE_EXIT=" + str(baseline_rc))
            else:
                print("LOCAL_COPY_BASELINE=REMOTE_NOT_CONFIGURED")
        print("SIMULATION=INCONCLUSIVE")
        return 2


def main():
    parser = argparse.ArgumentParser(
        description="Prueba OAuth sin alterar configuración real")
    parser.add_argument("--simulate-client", action="store_true",
                        help="simula un cliente roto usando exclusivamente /tmp")
    parser.add_argument("--remote-index", type=int, default=1,
                        help="índice 1..N, primero OneDrive, luego Google Drive (sin nombres)")
    parser.add_argument("--config", default=LOCAL_CONF)
    parser.add_argument("--key-file", default=AUTHORIZED_KEYS)
    opts = parser.parse_args()

    print("BRANCH=" + constants.CLOUD_BRANCH)
    print("WRITE_LIVE_CONFIG=NO")
    print("GITHUB_UPLOAD=NO")
    local = _read(opts.config)
    remote = _published(_key_from_file(opts.key_file))
    print("MQC2_DECRYPT=PASS")
    local_counts = rclone_token_policy.oauth_provider_counts(local)
    published_counts = rclone_token_policy.oauth_provider_counts(remote)
    print("LOCAL_GOOGLE_DRIVE_REMOTES=" + str(local_counts["drive"]))
    print("LOCAL_ONEDRIVE_REMOTES=" + str(local_counts["onedrive"]))
    print("PUBLISHED_GOOGLE_DRIVE_REMOTES=" + str(published_counts["drive"]))
    print("PUBLISHED_ONEDRIVE_REMOTES=" + str(published_counts["onedrive"]))
    _master_check(local, remote)
    if opts.simulate_client:
        return _client_simulation(remote, local=local, remote_index=opts.remote_index)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        # Evitar traceback: no se muestran valores ni líneas de credenciales.
        print("PILOT_ERROR=" + type(error).__name__)
        sys.exit(1)
