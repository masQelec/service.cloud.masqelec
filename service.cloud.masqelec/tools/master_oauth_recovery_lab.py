# -*- coding: utf-8 -*-
"""Prueba real y aislada de autorrecuperación MASTER (solo en /tmp).

El fichero operativo solo se abre en lectura; nunca se sustituyen credenciales,
se publican archivos ni se reinician servicios. Los módulos del laboratorio
se obtienen del commit fijo develop auditado, no del addon instalado.
"""
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import types
import urllib.request

SOURCE_COMMIT = "c3d1fa5fcf756da2ea594cdb308fba079dd22150"
SOURCE_BASE = (
    "https://raw.githubusercontent.com/masQelec/service.cloud.masqelec/"
    + SOURCE_COMMIT + "/service.cloud.masqelec/lib/"
)
LIVE_CONF = "/storage/.config/rclone/rclone.conf"
KEY_FILE = "/storage/.ssh/authorized_keys"
LIB_FILES = ("rclone_token_sync.py", "rclone_token_policy.py",
             "rclone_conf_merge.py", "chacha_pure.py")

LAB_STAGE = "BOOT"


def _safe_layout_report(label, raw, policy):
    """Mostrar únicamente recuentos de estructura; nunca nombres ni tokens."""
    try:
        sections = policy.sections(raw)
        tokens = policy.oauth_tokens(raw)
        counts = policy.oauth_provider_counts(raw)
    except (ValueError, UnicodeError, TypeError):
        print(label + "_STRUCTURE=INVALID")
        return
    print(label + "_SECTIONS=" + str(len(sections)))
    print(label + "_OAUTH_REMOTES=" + str(len(tokens)))
    print(label + "_AUXILIARY_SECTIONS=" + str(len(sections) - len(tokens)))
    print(label + "_ONEDRIVE=" + str(counts.get("onedrive", 0)))
    print(label + "_GOOGLE_DRIVE=" + str(counts.get("drive", 0)))
    onedrive = [sec for sec in sections.values()
                if sec.get("type", "").strip().lower() == "onedrive"]
    print(label + "_ONEDRIVE_NO_DRIVE_ID=" +
          str(sum(not sec.get("drive_id") for sec in onedrive)))
    print(label + "_ONEDRIVE_NO_DRIVE_TYPE=" +
          str(sum(not sec.get("drive_type") for sec in onedrive)))





def _download_modules(root):
    libdir = root / "lib"
    libdir.mkdir(mode=0o700)
    (libdir / "__init__.py").write_text("", encoding="ascii")
    for filename in LIB_FILES:
        req = urllib.request.Request(
            SOURCE_BASE + filename, headers={"User-Agent": "masQelec-oauth-lab/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            source = response.read(256 * 1024 + 1)
        if not source or len(source) > 256 * 1024:
            raise ValueError("Descarga de módulo inválida")
        (libdir / filename).write_bytes(source)
        os.chmod(libdir / filename, 0o600)
    (libdir / "constants.py").write_text(
        'CLOUD_BRANCH = "develop"\n'
        'CLOUD_RAW_BASE = "https://raw.githubusercontent.com/masQelec/cloud.masqelec/develop"\n'
        'RCLONE_TOKEN_SYNC_ENABLED = False\n',
        encoding="utf-8",
    )


def _get_key():
    with open(KEY_FILE, "rb") as stream:
        for raw in stream:
            line = raw.strip()
            if line and not line.startswith(b"#"):
                return hashlib.sha256(line).digest()
    raise ValueError("Clave de dispositivo no disponible")


def _rclone_binary():
    for path in ("/storage/.config/rclone/rclone", "/storage/.opt/bin/rclone",
                 "/usr/bin/rclone", "/usr/local/bin/rclone"):
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    binary = shutil.which("rclone")
    if binary:
        return binary
    raise ValueError("Ejecutable rclone no disponible")


def _corrupt_one_token(raw, merge):
    names, section, lines = 0, None, []
    for line in merge._lines(raw):
        match = merge._SECTION.match(line)
        if match:
            section = match.group(1)
        option = merge._OPTION.match(line)
        if option and option.group(1).lower() == "token" and names == 0:
            line = line[:line.index("=") + 1] + " {broken-test-json"
            names += 1
        lines.append(line)
    if names != 1:
        raise ValueError("No se pudo simular corrupción de token")
    return ("\n".join(lines).rstrip("\n") + "\n").encode("utf-8")


def _fake_modules(lab, key, binary):
    pkg = importlib.import_module("lib")
    for name in ("catalog_utils", "device_utils", "log_utils", "rclone_utils"):
        fake = types.ModuleType("lib." + name)
        sys.modules["lib." + name] = fake
        setattr(pkg, name, fake)

    def no_upload(*args, **kwargs):
        raise AssertionError("LAB_UPLOAD_FORBIDDEN")

    pkg.catalog_utils._upload_file = no_upload
    pkg.catalog_utils._gh_get_plain_token = lambda: ""
    pkg.device_utils.get_key_from_authorized_keys = lambda: key
    pkg.device_utils.is_master_device = lambda: True
    pkg.device_utils.get_device_role = lambda: "MASTER"
    pkg.log_utils.write_log = lambda *args, **kwargs: None
    pkg.rclone_utils.which_rclone = lambda: binary
    return importlib.import_module("lib.rclone_token_sync")


def main():
    global LAB_STAGE
    print("LAB_MODE=MASTER_CORRUPT_SELF_RECOVERY")
    print("ADDON_MODIFIED=NO")
    print("LIVE_RCLONE_CONF_WRITE=NO")
    print("GITHUB_UPLOAD=NO")
    print("MOUNT_RESTART=NO")
    print("CODE_REF=" + SOURCE_COMMIT)

    with tempfile.TemporaryDirectory(prefix="masqelec-master-selfrecover-", dir="/tmp") as name:
        root = Path(name)
        os.chmod(root, 0o700)
        LAB_STAGE = "DOWNLOAD_MODULES"
        _download_modules(root)
        LAB_STAGE = "IMPORT_MODULES"
        sys.path.insert(0, str(root))
        from lib import rclone_conf_merge as merge
        from lib import rclone_token_policy as policy
        LAB_STAGE = "READ_KEY"
        key = _get_key()
        LAB_STAGE = "FIND_RCLONE"
        binary = _rclone_binary()
        LAB_STAGE = "LOAD_WORKER"
        sync = _fake_modules(root, key, binary)

        LAB_STAGE = "READ_LOCAL"
        local = sync._read_stable(LIVE_CONF)
        _safe_layout_report("LOCAL", local, policy)
        LAB_STAGE = "VALIDATE_LOCAL_LAYOUT"
        policy.validate_master_layout(local)
        LAB_STAGE = "DOWNLOAD_DECRYPT_GITHUB"
        published = sync._remote_config(key)
        _safe_layout_report("GITHUB", published, policy)
        LAB_STAGE = "VALIDATE_GITHUB_LAYOUT"
        policy.validate_master_layout(published)
        LAB_STAGE = "COMPARE_IDENTITIES"
        if not merge.same_non_token_settings(local, published):
            print("LAB_RESULT=BLOCKED_DIFFERENT_REMOTE_IDENTITIES")
            return 2
        print("MQC2_AND_FOUR_REMOTES=PASS")
        LAB_STAGE = "CREATE_BROKEN_COPY"
        broken = _corrupt_one_token(local, merge)
        tmpconf = str(root / "rclone.conf")
        with open(tmpconf, "xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(broken)
        old = time.time() - 60
        os.utime(tmpconf, (old, old))
        sync.CONF_PATH = tmpconf
        sync._publish_master = lambda: (_ for _ in ()).throw(
            AssertionError("LAB_PUBLISH_FORBIDDEN")
        )
        LAB_STAGE = "FIRST_CORRUPTION_CHECK"
        first = sync._master_cycle(1000.0)
        print("CORRUPTION_FIRST_CHECK=" + first)
        if first != "master_corrupt_pending":
            print("LAB_RESULT=FAIL_FIRST_CHECK")
            return 2
        if Path(tmpconf).read_bytes() != broken:
            print("LAB_RESULT=FAIL_EARLY_WRITE")
            return 2
        LAB_STAGE = "SECOND_CORRUPTION_CHECK"
        second = sync._master_cycle(1061.0)
        print("CORRUPTION_SECOND_CHECK=" + second)
        if second != "master_recovered_restart_pending":
            print("LAB_RESULT=INCONCLUSIVE")
            return 2
        LAB_STAGE = "VERIFY_RECOVERY"
        recovered = Path(tmpconf).read_bytes()
        policy.validate_master_layout(recovered)
        if not merge.same_non_token_settings(recovered, published):
            print("LAB_RESULT=FAIL_RESTORED_IDENTITY")
            return 2
        backups = list(root.glob("rclone.conf.pre-master-recovery-*"))
        if len(backups) != 1 or backups[0].read_bytes() != broken:
            print("LAB_RESULT=FAIL_BACKUP")
            return 2
        if os.stat(tmpconf).st_mode & 0o777 != 0o600:
            print("LAB_RESULT=FAIL_FILE_PERMISSIONS")
            return 2
        if os.stat(backups[0]).st_mode & 0o777 != 0o600:
            print("LAB_RESULT=FAIL_BACKUP_PERMISSIONS")
            return 2
        print("BACKUP_ISOLATED_0600=PASS")
        print("RESTORED_LAYOUT=PASS")
        print("LAB_RESULT=PASS")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        # No exponer tracebacks: pueden contener rutas u otros valores sensibles.
        print("LAB_FAILED_AT=" + LAB_STAGE)
        print("LAB_RESULT=ERROR_" + type(exc).__name__)
        sys.exit(1)
