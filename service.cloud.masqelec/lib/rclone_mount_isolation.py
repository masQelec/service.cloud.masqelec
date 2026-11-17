# -*- coding: utf-8 -*-
"""Plan de aislamiento de rclone mount. NO modifica servicios ni credenciales.

Los cuatro montajes OneDrive usan dos cuentas. El plan crea una copia
privada por proceso para impedir escrituras simultáneas al mismo inode.
Una copia separada NO permite por sí sola actualizar un mount en caliente:
una recuperación debe verificarse, coordinar tokens y esperar remontaje seguro.
"""
import os
import re
import shlex
import tempfile

from lib import rclone_conf_merge as conf
from lib import rclone_token_policy as policy

LIVE_CONFIG = "/storage/.config/rclone/rclone.conf"
PROPOSED_DIR = "/storage/.config/rclone/isolated-mounts"

# Valores derivados de cloud.masqelec/develop/system.d/ (sin secretos).
MOUNT_SPECS = (
    ("rclone_tvshows_1.service", "users_library_1", "tvshows",
     "/storage/.mnt/tvshows/1"),
    ("rclone_tvshows_2.service", "users_library_2", "tvshows",
     "/storage/.mnt/tvshows/2"),
    ("rclone_videos_1.service", "users_library_1", "movies",
     "/storage/.mnt/videos/1"),
    ("rclone_videos_2.service", "users_library_2", "movies",
     "/storage/.mnt/videos/2"),
)


def _unit_text(raw):
    text = raw.decode("utf-8", "strict") if isinstance(raw, bytes) else raw
    if not isinstance(text, str):
        raise TypeError("Unidad systemd no es texto")
    return re.sub(r"\\\r?\n\s*", " ", text)


def _start_args(unit_raw):
    text = _unit_text(unit_raw)
    starts = [line.partition("=")[2].strip()
              for line in text.splitlines() if line.startswith("ExecStart=")]
    if len(starts) != 1:
        raise ValueError("Unidad debe contener un solo ExecStart")
    args = shlex.split(starts[0])
    if len(args) < 6 or os.path.basename(args[0]) != "rclone" or args[1] != "mount":
        raise ValueError("ExecStart no es un montaje rclone simple")
    return args


def _config_arg(args):
    paths = []
    for idx, arg in enumerate(args):
        if arg == "--config":
            if idx + 1 >= len(args):
                raise ValueError("Falta argumento de --config")
            paths.append(args[idx + 1])
        elif arg.startswith("--config="):
            paths.append(arg.partition("=")[2])
    if len(paths) != 1:
        raise ValueError("Unidad sin configuración única")
    return paths[0]


def _current_config_arg(args):
    value = _config_arg(args)
    if value != LIVE_CONFIG:
        raise ValueError("La unidad usa configuración inesperada")
    return value


def inspect_units(units):
    """Comprueba las cuatro unidades conocidas sin ejecutar systemctl."""
    if set(units) != {name for name, _, _, _ in MOUNT_SPECS}:
        raise ValueError("Inventario de unidades diferente del esperado")
    for unit, remote, subfolder, mount in MOUNT_SPECS:
        args = _start_args(units[unit])
        if args[2] != remote + ":" + subfolder or args[3] != mount:
            raise ValueError("Destino o fuente de montaje diferente")
        _current_config_arg(args)
    return True


def select_remote(raw_conf, name):
    """Construye config mínima de OneDrive con UNA sección exacta.

    No copia Google Drive, crypt, alias ni otras credenciales que el
    proceso de montaje no necesita.
    """
    all_lines = conf._lines(raw_conf)
    sections = conf._sections(all_lines)
    remote = sections.get(name)
    if not remote or remote.get("type", "").lower() != "onedrive":
        raise ValueError("Remoto OneDrive no encontrado")
    if not remote.get("drive_id") or not remote.get("drive_type"):
        raise ValueError("Identidad OneDrive incompleta")
    if name not in policy.oauth_tokens(raw_conf):
        raise ValueError("OAuth OneDrive inválido")
    selected, current = [], None
    for line in all_lines:
        found = conf._SECTION.match(line)
        if found:
            current = found.group(1)
        if current == name:
            selected.append(line)
    result = ("\n".join(selected).rstrip("\n") + "\n").encode("utf-8")
    if list(conf._sections(conf._lines(result))) != [name]:
        raise ValueError("Selección de configuración incorrecta")
    if policy.oauth_tokens(result)[name] != policy.oauth_tokens(raw_conf)[name]:
        raise ValueError("Token seleccionado no coincide")
    return result


def proposed_config_path(service):
    if service not in {name for name, _, _, _ in MOUNT_SPECS}:
        raise ValueError("Unidad no autorizada")
    return PROPOSED_DIR + "/" + service.removesuffix(".service") + ".conf"


def propose_unit(service, original):
    """Devuelve un borrador; no escribe ni recarga systemd."""
    if service not in {name for name, _, _, _ in MOUNT_SPECS}:
        raise ValueError("Unidad no autorizada")
    args = _start_args(original)
    _current_config_arg(args)
    source = original.decode("utf-8", "strict") if isinstance(original, bytes) else original
    search = "--config " + LIVE_CONFIG
    if source.count(search) != 1:
        raise ValueError("La unidad no tiene el patrón de configuración esperado")
    changed = source.replace(search, "--config " + proposed_config_path(service))
    if _config_arg(_start_args(changed)) != proposed_config_path(service):
        raise ValueError("No se sustituyó el origen de configuración")
    return changed.encode("utf-8")


def account_divergence(configs):
    """Compara refresh_token de los dos procesos por cada cuenta OneDrive.

    Solo indica igualdad/diferencia. No supone que el token con un mtime
    más reciente sea válido o más nuevo. Si difieren, se requiere una
    reconciliación validada antes de promover ninguno a MASTER/GitHub.
    """
    if set(configs) != {service for service, _, _, _ in MOUNT_SPECS}:
        raise ValueError("Faltan configuraciones de montaje")
    accounts = {}
    for service, remote, _, _ in MOUNT_SPECS:
        raw = configs[service]
        names = list(policy.oauth_tokens(raw))
        if names != [remote] or list(conf._sections(conf._lines(raw))) != [remote]:
            raise ValueError("Configuración aislada con remotos inesperados")
        options = policy.sections(raw)[remote]
        if options.get("type", "").lower() != "onedrive":
            raise ValueError("Proveedor inesperado")
        accounts.setdefault(remote, []).append(raw)
    result = {}
    for name, snapshots in accounts.items():
        if len(snapshots) != 2:
            raise ValueError("Se esperaban dos montajes por cuenta")
        if not conf.same_non_token_settings(*snapshots):
            raise ValueError("Identidad de una cuenta diferente entre montajes")
        a, b = (policy.oauth_tokens(raw)[name]["refresh_token"]
                for raw in snapshots)
        result[name] = "consistent" if a == b else "diverged"
    return result

def _atomic_private(path, contents):
    """Solo para escribir dentro del directorio temporal del laboratorio."""
    directory = os.path.dirname(path)
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=directory)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(contents)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def stage_in_directory(root, live_conf, units):
    """Genera borradores privados en ROOT controlado, nunca LIVE_CONFIG.

    Precondiciones: directorio root ya creado expresamente en /tmp y vacío,
    permisos 0700. No acepta un symlink como directorio.
    """
    if os.path.islink(root) or not os.path.isdir(root):
        raise ValueError("Directorio de laboratorio no seguro")
    if os.stat(root).st_mode & 0o777 != 0o700:
        raise ValueError("Directorio de laboratorio debe ser 0700")
    if os.listdir(root):
        raise ValueError("Directorio de laboratorio no está vacío")
    # KodiELEC puede resolver /tmp mediante un enlace a otro tmpfs.
    # Comparar ambos destinos reales; nunca aceptar una ruta fuera del
    # árbol autorizado aunque su texto empiece por '/tmp'.
    real_root = os.path.realpath(root)
    real_tmp = os.path.realpath("/tmp")
    if (real_root == real_tmp or
            os.path.commonpath((real_root, real_tmp)) != real_tmp):
        raise ValueError("Laboratorio fuera del directorio temporal seguro")
    policy.validate_master_layout(live_conf)
    inspect_units(units)
    for service, remote, _folder, _mount in MOUNT_SPECS:
        conf_path = os.path.join(root, service.removesuffix(".service") + ".conf")
        unit_path = os.path.join(root, service)
        _atomic_private(conf_path, select_remote(live_conf, remote))
        _atomic_private(unit_path, propose_unit(service, units[service]))
        with open(conf_path, "rb") as fd:
            if list(policy.oauth_tokens(fd.read())) != [remote]:
                raise ValueError("Fichero preparado con OAuth inesperado")
    return 4
