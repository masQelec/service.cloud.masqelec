# -*- coding: utf-8 -*-
"""Laboratorio SOLO LECTURA del aislamiento OneDrive (montajes intactos)."""
import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import urllib.request

REF = "23ec52b3b8662b43d2c2e871ae8ef5dedc44fd86"
SOURCE = ("https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/"
          + REF + "/service.cloud.masqelec/lib/")
UNITS = "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop/system.d/"
LIVE = "/storage/.config/rclone/rclone.conf"
LAB_STAGE = "BOOT"


def _fetch(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "masQelec-mount-isolation-lab/1.0",
        "Cache-Control": "no-cache"
    })
    with urllib.request.urlopen(req, timeout=30) as response:
        data = response.read(256 * 1024 + 1)
    if not data or len(data) > 256 * 1024:
        raise ValueError("Recurso de laboratorio inválido")
    return data


def _stable_live():
    if os.path.islink(LIVE):
        raise ValueError("Configuración operativa es symlink")
    pre = os.stat(LIVE)
    if not pre.st_size or pre.st_size > 1024 * 1024:
        raise ValueError("Tamaño inesperado de configuración")
    with open(LIVE, "rb") as fd:
        result = fd.read(1024 * 1024 + 1)
    post = os.stat(LIVE)
    if (len(result) != pre.st_size or pre.st_ino != post.st_ino or
            pre.st_size != post.st_size or pre.st_mtime_ns != post.st_mtime_ns):
        raise ValueError("Configuración modificada durante la lectura")
    return result


def run():
    global LAB_STAGE
    print("LAB_MODE=PER_MOUNT_ONEDRIVE_CONFIG_ISOLATION")
    print("SOURCE_REF=" + REF)
    print("LIVE_CONFIG_WRITE=NO")
    print("ADDON_WRITE=NO")
    print("SYSTEMD_WRITE=NO")
    print("MOUNT_RESTART=NO")
    print("GITHUB_UPLOAD=NO")
    LAB_STAGE = "CREATE_TMP"
    with tempfile.TemporaryDirectory(prefix="masqelec-mount-isolation-", dir="/tmp") as dirname:
        root = Path(dirname)
        os.chmod(root, 0o700)
        lib = root / "modules" / "lib"
        lib.mkdir(parents=True)
        os.chmod(lib.parent, 0o700)
        os.chmod(lib, 0o700)
        (lib / "__init__.py").write_bytes(b"")
        for file in ("rclone_mount_isolation.py", "rclone_conf_merge.py",
                     "rclone_token_policy.py"):
            LAB_STAGE = "DOWNLOAD_MODULES"
            target = lib / file
            target.write_bytes(_fetch(SOURCE + file))
            os.chmod(target, 0o600)
        LAB_STAGE = "IMPORT_MODULES"
        sys.path.insert(0, str(lib.parent))
        module = importlib.import_module("lib.rclone_mount_isolation")
        LAB_STAGE = "READ_LOCAL"
        original = _stable_live()
        LAB_STAGE = "DOWNLOAD_UNITS"
        units = {}
        for service, remote, _folder, _mount in module.MOUNT_SPECS:
            units[service] = _fetch(UNITS + service)
        LAB_STAGE = "VERIFY_UNITS"
        module.inspect_units(units)
        print("UNITS_MATCH_DEVELOP=PASS")
        # Diagnóstico estructural seguro: nunca imprime nombres ni tokens.
        # Detecta remotos renombrados en el conf real vs las unidades.
        LAB_STAGE = "CHECK_TEMP_ROOT"
        temp_base = os.path.realpath("/tmp")
        target = os.path.realpath(str(root / "proposal"))
        within_tmp = (target != temp_base and
                      os.path.commonpath((temp_base, target)) == temp_base)
        print("TEMP_REALPATH_SAFE=" + ("YES" if within_tmp else "NO"))
        LAB_STAGE = "PREFLIGHT_SELECTION"
        sections = module.policy.sections(original)
        for index, (service, remote, _folder, _mount) in enumerate(
                module.MOUNT_SPECS, 1):
            kind = sections.get(remote, {}).get("type", "").strip().lower()
            provider = ("CRYPT" if kind == "crypt" else
                        "ONEDRIVE" if kind == "onedrive" else
                        "DRIVE" if kind == "drive" else
                        "MISSING" if not kind else "OTHER")
            print("UNIT_{}_REMOTE_PROVIDER={}".format(index, provider))
            LAB_STAGE = "RESOLVE_DEPENDENCIES_{}".format(index)
            chain = module.dependency_closure(original, remote)
            oauth = module.policy.oauth_tokens(original)
            onedrive_dependencies = sum(
                sections[name].get("type", "").strip().lower() == "onedrive"
                for name in chain
            )
            print("UNIT_{}_CHAIN_SECTIONS={}".format(index, len(chain)))
            print("UNIT_{}_ONEDRIVE_DEPENDENCIES={}".format(
                index, onedrive_dependencies))
            print("UNIT_{}_OAUTH_DEPENDENCIES={}".format(
                index, len(chain.intersection(oauth))))
            if kind == "crypt":
                wrapper = sections[remote]
                filename_mode = wrapper.get("filename_encryption", "").lower()
                data_encryption_off = (
                    wrapper.get("no_data_encryption", "false").lower()
                    in ("true", "yes", "1")
                )
                print("UNIT_{}_FILENAME_ENCRYPTION={}".format(
                    index, "OFF" if filename_mode == "off" else
                    "DEFAULT_OR_OTHER"))
                print("UNIT_{}_DATA_ENCRYPTION={}".format(
                    index, "OFF" if data_encryption_off else "ON"))
            LAB_STAGE = "SELECT_REMOTE_{}".format(index)
            module.select_remote(original, remote)
            LAB_STAGE = "PROPOSE_UNIT_{}".format(index)
            module.propose_unit(service, units[service])
            print("UNIT_{}_PREPARED=PASS".format(index))
        LAB_STAGE = "STAGE_PRIVATE"
        destination = root / "proposal"
        destination.mkdir(mode=0o700)
        count = module.stage_in_directory(str(destination), original, units)
        print("ISOLATED_CONFIG_FILES=" + str(count))
        print("GENERATED_UNIT_PROPOSALS=" + str(count))
        LAB_STAGE = "VERIFY_ACCOUNTS"
        config_files = {}
        for service, remote, _, _ in module.MOUNT_SPECS:
            file = destination / (service.removesuffix(".service") + ".conf")
            config_files[service] = file.read_bytes()
        status = module.account_divergence(config_files)
        print("ONEDRIVE_ACCOUNTS=" + str(len(status)))
        print("ACCOUNT_TOKENS_CONSISTENT=" +
              str(sum(v == "consistent" for v in status.values())))
        print("ACCOUNT_TOKENS_DIVERGED=" +
              str(sum(v == "diverged" for v in status.values())))
        print("STAGED_FILES_MODE_0600=" +
              ("PASS" if all(os.stat(p).st_mode & 0o777 == 0o600
                             for p in destination.iterdir()) else "FAIL"))
        LAB_STAGE = "VERIFY_LIVE"
        refreshed = _stable_live()
        print("LIVE_CHANGED_DURING_LAB=" +
              ("NO" if refreshed == original else "YES"))
        print("LAB_RESULT=PASS")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    except Exception as exc:
        # No imprimir detalles de excepciones: pueden contener valores
        # sensibles de configuración o cabeceras de autenticación.
        print("LAB_FAILED_AT=" + LAB_STAGE)
        print("LAB_RESULT=ERROR_" + type(exc).__name__)
        sys.exit(1)
