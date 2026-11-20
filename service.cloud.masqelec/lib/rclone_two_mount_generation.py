# -*- coding: utf-8 -*-
"""P0-B: ventana de generaciones OAuth PURA. Sin IO, red, montajes o publish.

Un epoch fiable debe ser incrementado por TODOS los escritores del recurso.
rclone legacy NO participa: sus epochs no están coordinados. Por tanto,
NINGUNA respuesta de este módulo autoriza publicación/recovery ni despliegue.
No imprimir hashes, nombres OAuth, snapshots o secretos.
"""
import hashlib
import hmac
import re
import secrets

from lib import rclone_conf_merge as merge
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_oauth as oauth

_MAX_CONFIG = 1024 * 1024
_SHA = re.compile(r"[0-9a-f]{40}\Z")


class GenerationWindow:
    """Snapshot opaco: las huellas son HMAC efímeros; __repr__ no filtra."""

    __slots__ = ("_key", "_macs", "_epochs", "_sha", "_head",
                 "_trusted", "_baseline")

    def __init__(self, key, macs, epochs, sha, head, trusted, baseline):
        self._key = key
        self._macs = macs
        self._epochs = epochs
        self._sha = sha
        self._head = head
        self._trusted = trusted
        self._baseline = baseline

    def __repr__(self):
        return "<GenerationWindow redacted / lab-only>"

    @property
    def baseline(self):
        """Puede ser 'diverged'; no da derecho a elegir el refresh."""
        return self._baseline


def _check_meta(blob_sha, branch_head, epochs):
    if not isinstance(blob_sha, str) or not _SHA.fullmatch(blob_sha):
        raise ValueError("SHA remoto inválido")
    if not isinstance(branch_head, str) or not _SHA.fullmatch(branch_head):
        raise ValueError("Revisión de rama inválida")
    if (not isinstance(epochs, tuple) or len(epochs) != 4
            or any(type(v) is not int or v < 0 for v in epochs)):
        raise ValueError("Se requieren cuatro epochs monotónicos verificables")


def _check_sources(canonical, accounts, remote):
    if (not isinstance(accounts, tuple) or len(accounts) != 2
            or any(type(raw) is not bytes or not 0 < len(raw) <= _MAX_CONFIG
                   for raw in (canonical, accounts[0], accounts[1], remote))):
        raise ValueError("Snapshot inválido")
    policy.validate_master_layout(canonical)
    policy.validate_master_layout(remote)
    if not merge.same_non_token_settings(canonical, remote):
        raise ValueError("Identidades u opciones estáticas incompatibles")
    names = []
    for index, raw in enumerate(accounts):
        name, _token = oauth._account(canonical, index, raw)
        names.append(name)
    if len(set(names)) != 2:
        raise ValueError("Cuentas OneDrive duplicadas")
    local, published = policy.oauth_tokens(canonical), policy.oauth_tokens(remote)
    if set(local) != set(published):
        raise ValueError("Inventario OAuth incompatible")
    return "baseline_diverged" if any(
        local[name]["refresh_token"] != published[name]["refresh_token"]
        for name in local
    ) else "baseline_equal"


def _mac(key, label, data):
    return hmac.new(key, label + b"\0" + data, hashlib.sha256).digest()


def capture_window(canonical, accounts, remote, blob_sha, branch_head, epochs,
                   *, remote_authenticated=False, cooperative_epochs=False):
    """Captura un baseline autenticado POR EL LLAMADOR y sin exponer tokens.

    epochs=(canonical, account1, account2, remote), provistos por escritor
    que coordina *todos* los procesos. No existe todavía tal escritor en live.
    """
    if remote_authenticated is not True:
        raise ValueError("MQC2 no autenticado: bloqueo")
    if type(cooperative_epochs) is not bool:
        raise ValueError("Declaración de cooperación inválida")
    _check_meta(blob_sha, branch_head, epochs)
    baseline = _check_sources(canonical, accounts, remote)
    key = secrets.token_bytes(32)
    macs = tuple(_mac(key, label, raw) for label, raw in zip(
        (b"canonical", b"account1", b"account2", b"remote"),
        (canonical, accounts[0], accounts[1], remote)))
    return GenerationWindow(key, macs, epochs, blob_sha, branch_head,
                            cooperative_epochs, baseline)


def recheck_window(window, canonical, accounts, remote, blob_sha,
                   branch_head, epochs, *, remote_authenticated=False):
    """Responde SOLO estado de carrera; nunca devuelve permiso de publicar.

    Un cambio A->B->A se detecta únicamente si los epochs son fiables y
    avanzaron. Sin control de escritores reales: blocked_untracked_writers.
    """
    if not isinstance(window, GenerationWindow):
        return "blocked_invalid_window"
    if remote_authenticated is not True:
        return "blocked_unverified_remote"
    try:
        _check_meta(blob_sha, branch_head, epochs)
        _check_sources(canonical, accounts, remote)
    except (ValueError, TypeError, UnicodeError):
        return "blocked_invalid_sources"
    if epochs != window._epochs:
        return "changed_generation"
    if branch_head != window._head:
        return "changed_remote_revision"
    if blob_sha != window._sha:
        return "changed_remote_blob"
    for label, raw, expected in zip(
            (b"canonical", b"account1", b"account2", b"remote"),
            (canonical, accounts[0], accounts[1], remote),
            window._macs):
        if not hmac.compare_digest(_mac(window._key, label, raw), expected):
            return "changed_snapshot"
    if not window._trusted:
        return "blocked_untracked_writers"
    # Aun con una flota artificialmente coordinada, no es autorización:
    return "stable_for_lab_only"
