# -*- coding: utf-8 -*-
"""Política OAuth para Google Drive y OneDrive.

Las opciones no-token y la identidad de cada unidad deben permanecer iguales
durante una publicación automática. No se imprimen secretos.
Los access_token y sus expiry no definen la edad de un refresh_token.
"""
import hashlib
import json

from lib import rclone_conf_merge as conf


def sections(raw):
    return conf._sections(conf._lines(raw))


OAUTH_BACKENDS = ("drive", "onedrive")


def oauth_tokens(raw):
    """Tokens con refresh_token de remotos OAuth admitidos (drive y onedrive)."""
    result = {}
    for name, options in sections(raw).items():
        if options.get("type", "").strip().lower() not in OAUTH_BACKENDS:
            continue
        if "token" not in options:
            continue
        try:
            value = json.loads(options["token"])
        except (ValueError, TypeError):
            raise ValueError("OAuth token no es JSON válido")
        if not isinstance(value, dict) or not isinstance(
                value.get("refresh_token"), str) or not value["refresh_token"]:
            raise ValueError("OAuth sin refresh_token válido")
        result[name] = value
    return result



def validate_master_layout(raw):
    """Exige 2 OneDrive + 2 Drive, pero permite secciones no OAuth.

    rclone.conf puede incluir alias, crypt y otros remotos adicionales.
    Deben conservarse, no confundirse con los cuatro remotos OAuth. Un
    remoto drive/onedrive sin token es un fallo estructural, no un extra.
    """
    config = sections(raw)
    tokens = oauth_tokens(raw)
    counts = oauth_provider_counts(raw)
    declared_oauth = {
        name for name, options in config.items()
        if options.get("type", "").strip().lower() in OAUTH_BACKENDS
    }
    if (len(tokens) != 4 or counts != {"drive": 2, "onedrive": 2} or
            set(tokens) != declared_oauth):
        raise ValueError("Inventario MASTER OAuth incompleto o incompatible")
    for name in declared_oauth:
        options = config[name]
        if options.get("type", "").strip().lower() == "onedrive":
            if not options.get("drive_id") or not options.get("drive_type"):
                raise ValueError("Identidad OneDrive incompleta")
    return tuple(sorted(tokens))


def master_partial_identity_compatible(partial_raw, published_raw):
    """Validar campos de identidad presentes en un fichero dañado.

    No interpreta un remoto ausente como identidad cambiada, pero impide
    recuperar un token de otro proveedor/cuenta/unidad OneDrive.
    """
    published = sections(published_raw)
    try:
        current = sections(partial_raw)
    except (ValueError, UnicodeError):
        return True  # Ilegible: solo se usa copia remota MQC2 validada.
    for name, old in current.items():
        if name not in published:
            return False
        for key in conf._AUTH_IDENTITY:
            if key in old and old[key] != published[name].get(key, ""):
                return False
        # Alias/crypt/local y otras secciones auxiliares también importan:
        # no restaurar silenciosamente rutas o ajustes estáticos distintos.
        if old.get("type", "").strip().lower() not in OAUTH_BACKENDS:
            for key, value in old.items():
                if key != "token" and published[name].get(key) != value:
                    return False
    return True

def oauth_provider_counts(raw):
    """Contar remotos recuperables sin revelar nombres ni credenciales."""
    opts = sections(raw)
    compatible = oauth_tokens(raw)
    return {
        "drive": sum(opts[name].get("type", "").strip().lower() == "drive"
                     for name in compatible),
        "onedrive": sum(opts[name].get("type", "").strip().lower() == "onedrive"
                        for name in compatible),
    }


def changed_refresh_names(local_raw, published_raw):
    """Nombres internos de los remotos cuyo refresh_token difiere."""
    local, published = oauth_tokens(local_raw), oauth_tokens(published_raw)
    if set(local) != set(published):
        raise ValueError("Inventario OAuth diferente")
    return tuple(sorted(name for name in local
                        if local[name]["refresh_token"] !=
                        published[name]["refresh_token"]))


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


def master_should_publish(local_raw, published_raw):
    """Solo publicar si cambia algún refresh_token y opciones estables coinciden.

    OneDrive rota refresh_token durante renovaciones normales; access expiry
    no demuestra que el refresh token sea más reciente. La validez debe
    verificarse con rclone usando una configuración temporal, fuera de aquí.
    """
    local_conf = sections(local_raw)
    published_conf = sections(published_raw)
    if not local_conf or not published_conf or set(local_conf) != set(published_conf):
        raise ValueError("Cambió el inventario de remotos: revisión manual requerida")

    # Un cambio ajeno al token nunca debe llegar a GitHub por esta vía,
    # ni siquiera si también cambió un refresh_token.
    if not conf.same_non_token_settings(local_raw, published_raw):
        raise ValueError("Cambian opciones no OAuth: revisión manual requerida")

    local_tokens = oauth_tokens(local_raw)
    published_tokens = oauth_tokens(published_raw)
    if not local_tokens or set(local_tokens) != set(published_tokens):
        raise ValueError("Inventario de remotos OAuth incompatible")
    return bool(changed_refresh_names(local_raw, published_raw))


def tokens_from_master(local_raw, published_raw, broken_names,
                       allow_same_refresh=False):
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
        # Idéntico proveedor, credenciales y destino (drive_id/drive_type).
        if any(current[name].get(key, "") != published[name].get(key, "")
               for key in conf._AUTH_IDENTITY):
            raise ValueError("Identidad OAuth diferente: recuperación no automática")
        if (ours[name]["refresh_token"] == theirs[name]["refresh_token"]
                and not allow_same_refresh):
            raise ValueError("El MASTER no tiene un refresh_token diferente")
        if current[name].get("token") == published[name].get("token"):
            raise ValueError("No existe un token alternativo diferente")
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
    """Señal OAuth explícita; nunca confundir con cuota, permisos o red."""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    lower = (stderr or "").lower()
    if any(marker in lower for marker in (
        "timeout", "connection refused", "no such host", "dns",
        "rate limit", "ratelimit", "429", "throttl", "quota exceeded",
        "insufficientpermissions", "permission denied", "403",
        "forbidden", "access denied", "accessdenied",
        "network is unreachable",
    )):
        return False
    return any(marker in lower for marker in (
        "invalid_grant", "invalid_token", "invalid refresh token",
        "token has been expired or revoked", "authentication failed",
        "oauth2: cannot fetch token", "401 unauthorized", "unauthorized: 401",
        "status code: 401", "invalidauthenticationtoken",
        "invalidauthenticationtoken", "unauthenticated",
    ))
