# -*- coding: utf-8 -*-
"""Política pura para distribuir solamente renovaciones OAuth verificables.

No registra valores de token. Los cambios ordinarios de access_token/expiry
no requieren publicación: rclone los vuelve a obtener con refresh_token.
"""
import hashlib
import json
from datetime import datetime, timezone

from lib import rclone_conf_merge as conf


def sections(raw):
    return conf._sections(conf._lines(raw))


def oauth_tokens(raw):
    result = {}
    for name, options in sections(raw).items():
        # Los refresh_token de Box y otros proveedores pueden ser de un solo
        # uso: compartirlos entre dispositivos los invalidaría.
        if options.get("type", "").strip().lower() != "drive":
            continue
        if "token" not in options:
            continue
        try:
            value = json.loads(options["token"])
        except (ValueError, TypeError):
            raise ValueError("OAuth token no es JSON válido")
        if not isinstance(value, dict) or not value.get("refresh_token"):
            raise ValueError("OAuth sin refresh_token válido")
        result[name] = value
    return result


def stable_oauth_fingerprint(raw):
    """Huella para cambios de refresh_token y opciones, sin tokens volátiles."""
    config = sections(raw)
    oauth = oauth_tokens(raw)
    stable = {}
    for name, options in config.items():
        details = {k: v for k, v in options.items() if k != "token"}
        if name in oauth:
            details["_refresh"] = oauth[name]["refresh_token"]
        stable[name] = details
    canonical = json.dumps(stable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def token_expiry(value):
    """Fecha UTC del access token, o None si no existe (no confundir con refresh)."""
    raw = value.get("expiry")
    if not isinstance(raw, str):
        return None
    try:
        # Algunos JSON de rclone usan nanosegundos: limitar a microsegundos.
        ts = raw.rstrip("Z")
        if "." in ts:
            head, frac = ts.split(".", 1)
            ts = head + "." + frac[:6]
        instant = datetime.fromisoformat(ts)
        if instant.tzinfo is None:
            instant = instant.replace(tzinfo=timezone.utc)
        return instant.timestamp()
    except ValueError:
        return None


def master_should_publish(local_raw, published_raw):
    """Solo publicar refrescos; rechazar una credencial aparentemente antigua."""
    local_conf = sections(local_raw)
    published_conf = sections(published_raw)
    if not local_conf or not published_conf or set(local_conf) != set(published_conf):
        raise ValueError("Cambió el inventario de remotos: actualización manual requerida")
    for name, local_options in local_conf.items():
        previous = published_conf[name]
        if any(local_options.get(key, "") != previous.get(key, "")
               for key in conf._AUTH_IDENTITY):
            raise ValueError("Cambió la identidad del remoto: revisión manual requerida")

    local_tokens = oauth_tokens(local_raw)
    published_tokens = oauth_tokens(published_raw)
    if not local_tokens or set(local_tokens) != set(published_tokens):
        raise ValueError("No hay remotos OAuth compatibles")
    if stable_oauth_fingerprint(local_raw) == stable_oauth_fingerprint(published_raw):
        return False

    for name in local_tokens:
        old, new = published_tokens[name], local_tokens[name]
        if old["refresh_token"] != new["refresh_token"]:
            old_expiry, new_expiry = token_expiry(old), token_expiry(new)
            if old_expiry is not None and new_expiry is not None:
                if new_expiry + 60 < old_expiry:
                    raise ValueError("MASTER presenta una credencial anterior a la publicada")
    return True


def tokens_from_master(local_raw, published_raw, broken_names):
    """Actualiza únicamente tokens de remotos que han fallado por autenticación."""
    names = set(broken_names)
    local_lines = conf._lines(local_raw)
    current = sections(local_raw)
    published = sections(published_raw)
    ours = oauth_tokens(local_raw)
    theirs = oauth_tokens(published_raw)
    if not names or not names <= set(ours) or not names <= set(theirs):
        raise ValueError("No hay tokens recuperables para todos los remotos")
    replacements = {}
    for name in names:
        if any(current[name].get(key, "") != published[name].get(key, "")
               for key in conf._AUTH_IDENTITY):
            raise ValueError("Identidad OAuth diferente: recuperación no automática")
        if ours[name]["refresh_token"] == theirs[name]["refresh_token"]:
            raise ValueError("El MASTER no tiene un refresh_token diferente")
        replacements[name] = published[name]["token"]

    result, section = [], None
    for line in local_lines:
        found = conf._SECTION.match(line)
        if found:
            section = found.group(1)
        option = conf._OPTION.match(line)
        if option and option.group(1).lower() == "token" and section in replacements:
            line = line[:line.index("=") + 1] + " " + replacements[section]
        result.append(line)
    return ("\n".join(result).rstrip("\n") + "\n").encode("utf-8")


def auth_failure(stderr):
    """Sólo señales explícitas de autorización; no confundir red/timeout/cuotas."""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    lower = (stderr or "").lower()
    if any(m in lower for m in (
        "timeout", "connection refused", "no such host", "dns", "rate limit",
        "quota exceeded", "insufficientpermissions", "permission denied",
    )):
        return False
    return any(m in lower for m in (
        "invalid_grant", "invalid_token", "invalid refresh token",
        "token has been expired or revoked", "authentication failed",
        "oauth2: cannot fetch token", "401 unauthorized", "unauthorized: 401", "status code: 401",
    ))
