# -*- coding: utf-8 -*-
"""Explicitly gated CLIENT v2 OAuth recovery worker.

No effects at import. Real OneDrive/GitHub traffic is possible ONLY behind
the independent disabled release flag and after a confirmed account AUTH
probe of a PRIVATE COPY. No fallback to the legacy endpoint or publication.
"""
import os
import tempfile
import time

from lib import constants
from lib import rclone_two_mount_client_apply as apply
from lib import rclone_two_mount_master_runtime as master
from lib import rclone_two_mount_media_samples as media_samples
from lib import rclone_two_mount_live_adapter as live
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_plan as plan
from lib import rclone_token_policy as policy
from lib import rclone_token_sync as tokens
from lib import rclone_two_mount_boot_guard as guard

_last_attempt = None
_INTERVAL = 3600


def _probe_private(index, content):
    """Probe exactly one underlying OneDrive remote in 0700/0600 temp."""
    names = policy.oauth_tokens(content)
    if len(names) != 1:
        return "unavailable", b""
    name = next(iter(names))
    with tempfile.TemporaryDirectory(prefix="masqelec-client-probe-",
                                     dir="/tmp") as folder:
        os.chmod(folder, 0o700)
        path = os.path.join(folder, "account.conf")
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY |
                     getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        result = tokens._probe(name, path)
        if result != "ok":
            return result, b""
        # Probe can renew the refresh token. Only return the tested copy.
        from lib import rclone_two_mount_startup_stage as stage
        return "ok", stage._read_file(path, confidential=True)[0]


def _auth_state(index, account):
    result, _ = _probe_private(index, account)
    return result


def _media_check(index, known):
    if (type(index) is not int or index not in (0, 1) or
            not isinstance(known, (tuple, list)) or len(known) != 2):
        return False
    path = known[index]
    allowed = ("/storage/.mnt/videos/{}/".format(index+1),
               "/storage/.mnt/tvshows/{}/".format(index+1))
    if (type(path) is not str or not any(path.startswith(p) for p in allowed)
            or os.path.normpath(path) != path):
        return False
    return live.LocalAdapter._probe_known_media(path)


def tick(rpc_call, *, authorized=False, now=None,
         read_sources=None, transport=None, key=None, known=None,
         probe=None, role=None):
    """One bounded v2 CLIENT check. Returns status only, no OAuth bytes.

    Auth failures are account-scoped. Do not recover on rate limit, network
    errors, or unknown status. Credentials are never printed or uploaded.
    """
    global _last_attempt
    if authorized is not True:
        return "BLOCKED_NOT_AUTHORIZED"
    if (getattr(constants, "RCLONE_TWO_MOUNT_CLIENT_RECOVERY_ENABLED", False)
            is not True or
            getattr(constants, "RCLONE_TWO_MOUNT_FEATURE_ALLOWED", False)
            is not True or constants.CLOUD_BRANCH != "develop"):
        return "BLOCKED_RELEASE_GATES"
    if (role if role is not None else apply._get_role()) != "CLIENT":
        return "BLOCKED_NOT_CLIENT"
    if rollout.mode(True) != "active" or guard.client_recovery_pending():
        return "BLOCKED_NOT_ACTIVE_OR_RECOVERY"
    if not apply.kodi_idle.is_playback_idle(rpc_call):
        return "DEFERRED_PLAYBACK"
    clock = time.monotonic() if now is None else now
    if _last_attempt is not None and clock - _last_attempt < _INTERVAL:
        return "DEFERRED_INTERVAL"
    _last_attempt = clock
    try:
        local = read_sources if read_sources is not None else master._local_sources
        canonical, accounts = local()
        if not isinstance(accounts, (list, tuple)) or len(accounts) != 2:
            return "BLOCKED_SOURCES"
        for index, account in enumerate(accounts):
            if _auth_state(index, account) != "auth":
                continue
            actual_known = known if known is not None else media_samples.discover()
            if not actual_known:
                return "BLOCKED_MEDIA"
            secret = key if key is not None else master._get_device_key()
            gh = transport
            if gh is None:
                token = master._get_gh_token()
                if not token:
                    return "BLOCKED_GITHUB_AUTH"
                gh = master.GitHubV2Transport(token)
            return apply.recover_one(
                account_index=index, auth_status="auth",
                read_sources=local, head=gh.head, get=gh.get,
                probe=probe if probe is not None else _probe_private,
                key=secret, rpc_call=rpc_call,
                media_check=lambda i: _media_check(i, actual_known),
                authorized=True)
        return "HEALTHY_OR_UNAVAILABLE"
    except (OSError, ValueError, TypeError, RuntimeError, KeyError,
            UnicodeError, OverflowError):
        return "BLOCKED_WORKER_ERROR"
