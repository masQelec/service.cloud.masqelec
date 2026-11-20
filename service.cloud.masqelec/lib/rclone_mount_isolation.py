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


def _remote_reference(value):
    """Dependencia nombrada 'remoto:ruta'; no admite rutas locales ni inline."""
    if not value or not isinstance(value, str) or ":" not in value:
        raise ValueError("Referencia de remoto no soportada")
    name = value.split(":", 1)[0]
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,63}", name):
        raise ValueError("Referencia remota no segura o no nombrada")
    return name


def dependency_closure(raw_conf, name):
    """Obtiene la cadena completa de backends de un montaje.

    Soporta remotos OAuth directos, alias/crypt/chunker y múltiples
    upstreams de combine/union. Falla si hay referencias locales, remotos
    inexistentes, ciclos o tipos que no podemos analizar de forma segura.
    """
    sections = conf._sections(conf._lines(raw_conf))
    tokens = policy.oauth_tokens(raw_conf)  # Validar JSON OAuth en todos.
    active, complete, used_oauth = set(), set(), set()

    def walk(current):
        if current in active:
            raise ValueError("Ciclo entre remotos virtuales")
        if current in complete:
            return
        if current not in sections:
            raise ValueError("Dependencia de remoto ausente")
        opts = sections[current]
        backend = opts.get("type", "").strip().lower()
        active.add(current)
        try:
            if backend in ("onedrive", "drive"):
                if current not in tokens:
                    raise ValueError("Remoto OAuth sin refresh_token")
                if backend == "onedrive" and (
                        not opts.get("drive_id") or not opts.get("drive_type")):
                    raise ValueError("Identidad OneDrive incompleta")
                used_oauth.add(current)
            elif backend in ("alias", "crypt", "chunker"):
                walk(_remote_reference(opts.get("remote", "")))
            elif backend in ("union", "combine"):
                upstreams = opts.get("upstreams", "")
                try:
                    parts = shlex.split(upstreams)
                except ValueError:
                    raise ValueError("Lista de upstreams inválida")
                if not parts:
                    raise ValueError("Remoto virtual sin upstreams")
                for item in parts:
                    remote_path = item
                    if backend == "combine":
                        label, sep, remote_path = item.partition("=")
                        if not sep or not label or not remote_path:
                            raise ValueError("Upstream combine inválido")
                    walk(_remote_reference(remote_path))
            else:
                raise ValueError("Backend de remoto no verificado")
            complete.add(current)
        finally:
            active.remove(current)

    walk(name)
    if not used_oauth:
        raise ValueError("Montaje sin credenciales OAuth verificables")
    return frozenset(complete)


def select_remote(raw_conf, name):
    """Extrae el remoto solicitado y todas sus dependencias, sin inventarlas.

    Conserva las secciones originales completas, en el orden original.
    OAuth, wrappers y rutas internas mantienen los valores exactos.
    """
    selected = dependency_closure(raw_conf, name)
    result, current = [], None
    for line in conf._lines(raw_conf):
        found = conf._SECTION.match(line)
        if found:
            current = found.group(1)
        if current in selected:
            result.append(line)
    raw = ("\n".join(result).rstrip("\n") + "\n").encode("utf-8")
    sections = conf._sections(conf._lines(raw))
    if set(sections) != selected:
        raise ValueError("Faltan secciones en la configuración aislada")
    originals = policy.oauth_tokens(raw_conf)
    for remote, token in policy.oauth_tokens(raw).items():
        if token != originals[remote]:
            raise ValueError("Token cambiado al preparar la configuración")
    if dependency_closure(raw, name) != selected:
        raise ValueError("Dependencias no conservadas")
    return raw


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
    """Compara por nombre cada credencial OAuth compartida entre montajes.

    No elige ganadores automáticamente; una discrepancia exige validación
    independiente antes de propagar credenciales a los otros procesos.
    """
    if set(configs) != {service for service, _, _, _ in MOUNT_SPECS}:
        raise ValueError("Faltan configuraciones de montaje")
    accounts = {}
    for service, remote, _, _ in MOUNT_SPECS:
        raw = configs[service]
        expected = dependency_closure(raw, remote)
        if set(policy.sections(raw)) != expected:
            raise ValueError("Configuración aislada contiene secciones ajenas")
        all_opts = policy.sections(raw)
        for name, token in policy.oauth_tokens(raw).items():
            accounts.setdefault(name, []).append((all_opts[name], token))
    status = {}
    for name, snapshots in accounts.items():
        non_tokens = [{k: v for k, v in opts.items() if k != "token"}
                      for opts, token in snapshots]
        if any(opts != non_tokens[0] for opts in non_tokens):
            raise ValueError("Identidad OAuth diferente entre montajes")
        tokens = [token["refresh_token"] for opts, token in snapshots]
        status[name] = ("single_mount" if len(tokens) == 1 else
                        "consistent" if len(set(tokens)) == 1 else "diverged")
    return status

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
            config = fd.read()
        if (dependency_closure(config, remote) !=
                frozenset(policy.sections(config))):
            raise ValueError("Fichero preparado con dependencias extrañas")
    return 4
