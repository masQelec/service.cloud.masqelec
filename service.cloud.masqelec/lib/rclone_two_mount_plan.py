# -*- coding: utf-8 -*-
"""Plan SIN DESPLIEGUE: 2 rclone crypt raíz + 4 bind, legacy paths intactos.

No instala ni habilita unidades. Nunca guarda credenciales en cloud/GitHub.
El contenido OAuth y crypt se obtiene del rclone.conf local validado.
"""
import hashlib
import json
import os
import shlex
import tempfile

from lib import rclone_mount_isolation as isolation
from lib import rclone_token_policy as policy
from lib import rclone_two_mount_rollout as rollout

LAYOUT = rollout.LAYOUT
FUSE_ROOTS = (
    "/storage/.mnt/cloud/1",
    "/storage/.mnt/cloud/2",
)
ACCOUNT_CONFS = (
    "/storage/.config/rclone/isolated-mounts/account1.conf",
    "/storage/.config/rclone/isolated-mounts/account2.conf",
)
ACCOUNT_REMOTES = ("users_library_1", "users_library_2")
ACCOUNT_UNITS = rollout.NEW_SERVICES
# Compatibilidad: rutas de Kodi no pueden variar ni un carácter.
BIND_MAP = (
    ("masqelec_bind_tvshows_1.service", 0, "tvshows",
     "/storage/.mnt/tvshows/1"),
    ("masqelec_bind_tvshows_2.service", 1, "tvshows",
     "/storage/.mnt/tvshows/2"),
    ("masqelec_bind_videos_1.service", 0, "movies",
     "/storage/.mnt/videos/1"),
    ("masqelec_bind_videos_2.service", 1, "movies",
     "/storage/.mnt/videos/2"),
)


def _read_options(unit_text):
    args = isolation._start_args(unit_text)
    isolation._current_config_arg(args)
    if "--daemon" in args or "--rc" in args:
        raise ValueError("Unidad incompatible con montaje raíz gestionado")
    return args


def _normalized_flags(args):
    rest = args[4:]
    flags = []
    index = 0
    while index < len(rest):
        flag = rest[index]
        if flag in ("--config", "--log-file"):
            if index + 1 >= len(rest):
                raise ValueError("Falta valor de argumento rclone")
            index += 2
            continue
        if flag.startswith("--config=") or flag.startswith("--log-file="):
            index += 1
            continue
        flags.append(flag)
        index += 1
    return tuple(flags)


def validate_legacy_units(units):
    """Comprueba emparejamiento y opciones consistentes entre movies/tvshows."""
    isolation.inspect_units(units)
    for index in (0, 1):
        t = _read_options(units["rclone_tvshows_{}.service".format(index + 1)])
        v = _read_options(units["rclone_videos_{}.service".format(index + 1)])
        if _normalized_flags(t) != _normalized_flags(v):
            raise ValueError("Opciones entre películas y series diferentes")
        if "--read-only" not in _normalized_flags(t):
            raise ValueError("Montaje de origen no es solo lectura")
    return True


def account_snapshot(raw_conf, account_index):
    """Un wrapper crypt + exactamente un OAuth OneDrive por cuenta."""
    if account_index not in (0, 1):
        raise ValueError("Cuenta no permitida")
    policy.validate_master_layout(raw_conf)
    remote = ACCOUNT_REMOTES[account_index]
    sections = policy.sections(raw_conf)
    if sections.get(remote, {}).get("type", "").strip().lower() != "crypt":
        raise ValueError("La raíz no es crypt")
    # Preservar modo de nombres; no cambiar criptografía existente.
    dependencies = isolation.dependency_closure(raw_conf, remote)
    selected = isolation.select_remote(raw_conf, remote)
    underlying = policy.oauth_tokens(selected)
    if len(underlying) != 1 or len(dependencies) != 2:
        raise ValueError("Cadena crypt/OneDrive no es unívoca")
    underlying_name = next(iter(underlying))
    if policy.sections(selected)[underlying_name].get("type") != "onedrive":
        raise ValueError("El proveedor subyacente no es OneDrive")
    return selected


def _root_unit(index, legacy_unit):
    args = _read_options(legacy_unit)
    args[2] = ACCOUNT_REMOTES[index] + ":"
    args[3] = FUSE_ROOTS[index]
    config = isolation._config_arg(args)
    if config != isolation.LIVE_CONFIG:
        raise ValueError("Origen de credenciales inesperado")
    position = args.index("--config")
    args[position + 1] = ACCOUNT_CONFS[index]
    if "--log-file" in args:
        pos = args.index("--log-file")
        args[pos + 1] = "/storage/.kodi/temp/rclone_library_{}.log".format(index+1)
    start = " ".join(shlex.quote(arg) for arg in args)
    target = FUSE_ROOTS[index]
    return (
        "[Unit]\n"
        "Description=masQelec TwoMount library {} (STAGED PILOT)\n"
        "Wants=network-online.target\nAfter=network-online.target\n"
        "Requires=network-online.target\n\n"
        "[Service]\n"
        "Type=notify\nNotifyAccess=main\n"
        "User=root\nGroup=root\nLimitNOFILE=65535\n"
        "KillMode=mixed\nKillSignal=SIGINT\nTimeoutStopSec=30\n"
        "TimeoutStartSec=120\n"
        "ExecStartPre=/bin/mkdir -p {}\n"
        "ExecStart={}\n"
        "ExecStop=/bin/fusermount -uz {}\n"
        "Restart=on-failure\nRestartSec=5\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    ).format(index+1, target, start, target).encode("utf-8")


def _bind_unit(name, account_index, folder, target):
    """Bind de Linux; sin proceso rclone adicional."""
    account_unit = ACCOUNT_UNITS[account_index]
    source = FUSE_ROOTS[account_index] + "/" + folder
    return (
        "[Unit]\n"
        "Description=masQelec bind {} (STAGED PILOT)\n"
        "BindsTo={}\nAfter={}\n\n"
        "[Service]\nType=oneshot\nRemainAfterExit=yes\n"
        "ExecStartPre=/bin/mkdir -p {}\n"
        "ExecStartPre=/bin/mountpoint -q {}\n"
        "ExecStartPre=/bin/test -d {}\n"
        "ExecStartPre=/bin/sh -c '! /bin/mountpoint -q {}'\n"
        "ExecStart=/bin/mount --bind {} {}\n"
        "ExecStop=/bin/umount {}\n\n"
        "[Install]\nWantedBy=multi-user.target\n"
    ).format(name, account_unit, account_unit,
             target, FUSE_ROOTS[account_index], source, target,
             source, target, target).encode("utf-8")


def generate(raw_conf, legacy_units):
    """Devuelve mapa de archivos (nombre,bytes,permisos); sin tocar disco."""
    validate_legacy_units(legacy_units)
    result = {}
    for i in (0, 1):
        result["account{}.conf".format(i+1)] = (
            account_snapshot(raw_conf, i), 0o600)
        base = "rclone_tvshows_{}.service".format(i+1)
        result[ACCOUNT_UNITS[i]] = (_root_unit(i, legacy_units[base]), 0o644)
    for name, i, folder, dst in BIND_MAP:
        result[name] = (_bind_unit(name, i, folder, dst), 0o644)
    return result


def public_manifest(artifacts):
    """Incluye hashes SOLO de unidades; jamás hashes de secretos OAuth."""
    units = {name: hashlib.sha256(data).hexdigest()
             for name, (data, _mode) in artifacts.items()
             if name.endswith(".service")}
    if len(units) != 6:
        raise ValueError("Se esperaban seis unidades")
    return {
        "schema": rollout.SCHEMA,
        "layout": rollout.LAYOUT,
        "candidate_id": rollout.CANDIDATE_ID,
        "activation": "operator_only",
        "credential_source": "local_mqc2_verified",
        "kodi_paths_unchanged": True,
        "rclone_processes": 2,
        "oauth_writers_per_account_per_device": 1,
        "unit_sha256": units,
    }


def _write_private(path, content, mode):
    fd, temp = tempfile.mkstemp(prefix=".staging-", dir=os.path.dirname(path))
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as out:
            out.write(content)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def stage_to_tmp(destination, raw_conf, legacy_units):
    """Solo en /tmp privado 0700 y vacío. Ningún cambio en /storage."""
    real = os.path.realpath(destination)
    tmp_root = os.path.realpath("/tmp")
    if (os.path.islink(destination) or not os.path.isdir(destination)
            or os.stat(destination).st_mode & 0o777 != 0o700
            or os.path.commonpath((real, tmp_root)) != tmp_root
            or real == tmp_root or os.listdir(destination)):
        raise ValueError("Destino de ensayo no seguro ni vacío")
    artifacts = generate(raw_conf, legacy_units)
    manifest = public_manifest(artifacts)
    for name, (data, mode) in artifacts.items():
        _write_private(os.path.join(destination, name), data, mode)
    _write_private(
        os.path.join(destination, "rollout-manifest.json"),
        (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(),
        0o600,
    )
    return manifest
