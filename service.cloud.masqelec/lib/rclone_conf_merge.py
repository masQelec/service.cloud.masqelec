# -*- coding: utf-8 -*-
"""Fusión conservadora de rclone.conf. No guarda ni registra secretos."""
import re

_SECTION = re.compile(r"^\s*\[([^\]\r\n]+)\]\s*$")
_OPTION = re.compile(r"^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$")
_AUTH_IDENTITY = ("type", "client_id", "client_secret", "scope",
                  "service_account_file", "service_account_credentials",
                  "env_auth", "team_drive", "root_folder_id")


def _lines(raw):
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "strict")
    if not isinstance(raw, str):
        raise TypeError("rclone.conf debe contener texto UTF-8")
    return raw.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff").splitlines()


def _sections(lines):
    sections = {}
    current = None
    for line in lines:
        match = _SECTION.match(line)
        if match:
            current = match.group(1)
            if current in sections:
                raise ValueError("Sección duplicada en rclone.conf")
            sections[current] = {}
            continue
        match = _OPTION.match(line)
        if match and current is not None:
            key = match.group(1).lower()
            if key in sections[current]:
                raise ValueError("Opción duplicada en rclone.conf")
            sections[current][key] = match.group(2).strip()
    return sections


def preserve_local_oauth_tokens(remote_raw, local_raw):
    """Conserva token local si el remoto mantiene la misma identidad OAuth.

    Si el remoto añade/elimina remotos o cambia credenciales de autenticación,
    prevalece el token remoto. No modifica el objeto local en disco.
    """
    remote_lines = _lines(remote_raw)
    local_lines = _lines(local_raw)
    remote_sections = _sections(remote_lines)
    local_sections = _sections(local_lines)
    local_tokens = {}
    for name, remote in remote_sections.items():
        old = local_sections.get(name)
        if not old or not remote.get("token") or not old.get("token"):
            continue
        if all(remote.get(key, "") == old.get(key, "")
               for key in _AUTH_IDENTITY):
            local_tokens[name] = old["token"]

    result = []
    current = None
    for line in remote_lines:
        match = _SECTION.match(line)
        if match:
            current = match.group(1)
        option = _OPTION.match(line)
        if option and current in local_tokens and option.group(1).lower() == "token":
            prefix = line[:line.index("=") + 1]
            line = prefix + " " + local_tokens[current]
        result.append(line.rstrip())
    return ("\n".join(result).rstrip("\n") + "\n").encode("utf-8")


def compare_non_token_settings(local_raw, remote_raw):
    """Diagnóstico: nombres de claves diferentes, jamás sus valores ni secciones."""
    local = _sections(_lines(local_raw))
    remote = _sections(_lines(remote_raw))
    if local == remote:
        return ()
    differences = set()
    for name in set(local) | set(remote):
        old = local.get(name)
        new = remote.get(name)
        if old is None or new is None:
            differences.add("sections")
            continue
        for key in set(old) | set(new):
            if key != "token" and old.get(key) != new.get(key):
                differences.add(key)
    return tuple(sorted(differences))

def same_non_token_settings(local_raw, remote_raw):
    """Compara opciones efectivas ignorando token, comentarios y formato."""
    def normalized(raw):
        return {
            name: {key: value for key, value in options.items() if key != "token"}
            for name, options in _sections(_lines(raw)).items()
        }
    return normalized(local_raw) == normalized(remote_raw)
