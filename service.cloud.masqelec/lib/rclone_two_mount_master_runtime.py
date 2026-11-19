# -*- coding: utf-8 -*-
"""Adaptador MASTER para GitHub MQC2 v2, desactivado por defecto.

No se invoca hasta que feature y publicación MASTER estén habilitadas en
la release validada. Nunca escribe al antiguo rclone/rclone.conf.crypt.
"""
import json
import os
import stat
import tempfile
import urllib.parse

from lib import constants
from lib import rclone_two_mount_config_routes as routes
from lib import rclone_two_mount_master_sync as master
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_startup_stage as stage

API = "https://api.github.com/repos/masQelec/cloud.masqelec"
BRANCH = "develop"
MAX_HTTP_BODY = 8 * 1024 * 1024


class GitHubV2Transport:
    """Solo la rama develop del cloud repo; path remoto fijo, nunca fallback."""
    def __init__(self, token, request=None):
        if not isinstance(token, str) or not token:
            raise ValueError("GitHub token required")
        self._token = token
        if request is None:
            from lib import catalog_utils
            request = catalog_utils._req
        self._request = request
        if not callable(self._request):
            raise ValueError("GitHub request callback required")

    def _call(self, method, url, payload=None):
        status, body = self._request(
            method, url, self._token, payload)
        if type(status) is not int:
            return None, None
        if isinstance(body, (str, bytes)) and len(body) > MAX_HTTP_BODY:
            return None, None
        return status, body

    def head(self):
        status, body = self._call(
            "GET", API + "/branches/" + BRANCH)
        if status != 200:
            return None
        try:
            data = json.loads(body) if isinstance(
                body, (str, bytes)) else body
            return data["commit"]["sha"]
        except (ValueError, KeyError, TypeError, AttributeError):
            return None

    def get(self, path):
        if path != routes.V2_REMOTE_PATH:
            raise ValueError("GitHub path outside v2 allowlist")
        return self._call(
            "GET", API + "/contents/" +
            urllib.parse.quote(path, safe="/") + "?ref=" + BRANCH)

    def put(self, path, payload):
        if path != routes.V2_REMOTE_PATH:
            raise ValueError("GitHub path outside v2 allowlist")
        if (not isinstance(payload, dict) or
                payload.get("branch") != BRANCH):
            raise ValueError("Invalid GitHub branch")
        return self._call(
            "PUT", API + "/contents/" +
            urllib.parse.quote(path, safe="/"), payload)


def _local_sources():
    # No seguir enlaces, exigir 0600 y snapshot estable de cada fuente.
    paths = (stage.LOCAL_CONF,) + plan.ACCOUNT_CONFS
    result = []
    for path in paths:
        raw, _ = stage._read_file(path, confidential=True)
        meta = os.lstat(path)
        if (meta.st_uid != os.geteuid() or
                not stat.S_ISREG(meta.st_mode) or
                stat.S_IMODE(meta.st_mode) != 0o600):
            raise ValueError("Untrusted local OAuth config")
        result.append(raw)
    return result[0], (result[1], result[2])


def _probe_candidate(candidate, names):
    """Sondeo explícito, solo con flag de release y en archivo temporal 0600.

    Una copia de rclone.conf puede rotar los tokens dentro del temporal;
    el motor exige releer y comparar las fuentes originales antes de PUT.
    """
    with tempfile.TemporaryDirectory(
            prefix="masqelec-v2-master-probe-", dir="/tmp") as folder:
        os.chmod(folder, 0o700)
        path = os.path.join(folder, "rclone-check.conf")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        from lib import rclone_token_sync as tokens
        return {name: tokens._probe(name, path) for name in names}



def _get_role():
    from lib import device_utils
    return device_utils.get_device_role()


def _get_device_key():
    from lib import device_utils
    return device_utils.get_key_from_authorized_keys()


def _get_gh_token():
    from lib import catalog_utils
    return catalog_utils._gh_get_plain_token()


def run_once(*, release_authorized=False, request=None,
             sources=None, probe=None, key=None, token=None):
    """Una iteración MASTER; SIN autorización explícita no lee ni conecta.

    No forma parte de la release actual. El montaje v2 debe estar ACTIVO
    y con la bandera propia de sincronización habilitada.
    """
    if release_authorized is not True:
        return "blocked_not_authorized"
    if (getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED", False)
            is not True or
            constants.CLOUD_BRANCH != BRANCH or
            _get_role() != "MASTER" or
            rollout.mode(True) != "active"):
        return "blocked_master_not_ready"
    try:
        secret_key = key if key is not None else (
            _get_device_key())
        gh_token = token if token is not None else (
            _get_gh_token())
        if not secret_key or not gh_token:
            return "blocked_missing_credentials"
        gh = GitHubV2Transport(gh_token, request=request)
        return master.sync_once(
            sources if sources is not None else _local_sources,
            gh.head, gh.get, gh.put,
            probe if probe is not None else _probe_candidate,
            secret_key, gh_token, release_authorized=True,
            master_attested=True)
    except (OSError, ValueError, KeyError, TypeError, RuntimeError):
        return "blocked_master_runtime"

def publish_from_legacy_before_cutover(*, authorized=False, request=None,
                                      probe=None, key=None, token=None):
    """MASTER-only: publish authenticated MQC2 v2 while four FUSE remain on.

    Uses read-only snapshots of the existing, verified local canonical
    config and legacy service definitions; does not install a mount.
    The master_sync engine probes OAuth and does GitHub CAS/readback.
    """
    if authorized is not True:
        return "blocked_not_authorized"
    if (constants.CLOUD_BRANCH != BRANCH
            or getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED",
                       False) is not True
            or getattr(constants, "RCLONE_TWO_MOUNT_MASTER_SYNC_ENABLED",
                       False) is not True
            or _get_role() != "MASTER"
            or rollout.mode(True) != "legacy"):
        return "blocked_master_not_ready"
    try:
        secret = _get_device_key() if key is None else key
        github_token = _get_gh_token() if token is None else token
        if not secret or not github_token:
            return "blocked_missing_credentials"
        gh = GitHubV2Transport(github_token, request=request)

        def local_sources():
            canonical, legacy_units, _ = stage._read_sources(
                stage.LOCAL_CONF, stage.LEGACY_UNIT_DIR)
            # Validate both existing service configurations BEFORE publish.
            plan.generate(canonical[0], legacy_units)
            return canonical[0], (
                plan.account_snapshot(canonical[0], 0),
                plan.account_snapshot(canonical[0], 1),
            )

        return master.sync_once(
            local_sources, gh.head, gh.get, gh.put,
            probe if probe is not None else _probe_candidate,
            secret, github_token, release_authorized=True,
            master_attested=True)
    except (OSError, ValueError, TypeError, KeyError, RuntimeError):
        return "blocked_master_runtime"
