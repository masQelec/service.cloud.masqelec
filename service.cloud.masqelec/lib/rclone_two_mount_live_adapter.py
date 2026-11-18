# -*- coding: utf-8 -*-
"""Adaptador local EN DESARROLLO para motor 4 FUSE -> 2 FUSE + 4 bind.

No importado por service.py ni expuesto como comando --apply. Se crea con
live_enabled=False por defecto, que bloquea CUALQUIER operación mutable.
Aún requiere pruebas integradas con systemd/KodiELEC y recuperación de reboot.
No hay autorización de despliegue.
"""
import os
import shutil
import stat
import sys
import subprocess
import tempfile
import time

from lib import rclone_two_mount_atomic_install as atomic
from lib import rclone_two_mount_cutover_engine as engine
from lib import rclone_two_mount_health as health
from lib import rclone_two_mount_journal as journal
from lib import rclone_two_mount_kodi_idle as kodi_idle
from lib import rclone_two_mount_plan as plan
from lib import rclone_two_mount_rollout as rollout
from lib import rclone_two_mount_startup_stage as stage
from lib import rclone_two_mount_token_rollback as oauth
from lib import rclone_conf_merge as conf


TXN_PARENT = "/storage/.config/masqelec/rclone-v2-transaction"


class LocalAdapter:
    """Inyección explícita de acceso real: por defecto NUNCA ejecuta."""

    def __init__(self, rpc_call=None, *, live_enabled=False,
                 canonical=stage.LOCAL_CONF, unit_dir=stage.LEGACY_UNIT_DIR,
                 account_confs=plan.ACCOUNT_CONFS, state_path=rollout.STATE_PATH,
                 txn_parent=TXN_PARENT, runner=None, mount_reader=None,
                 known_media_files=()):
        self.rpc = rpc_call
        self.enabled = live_enabled is True
        self.canonical = canonical
        self.unit_dir = unit_dir
        self.account_confs = tuple(account_confs)
        self.state_path = state_path
        self.txn_parent = txn_parent
        self.runner = runner if runner is not None else self._system_runner
        self.mount_reader = (mount_reader if mount_reader is not None
                             else self._system_mountinfo)
        self.baseline = None
        self.units = None
        self.txn = None
        self.at_stop = None
        self.candidate = None
        self.installed = {}
        self.started_roots = set()
        self.attempted_binds = set()
        self.known_media_files = tuple(known_media_files)

    def _require_enabled(self):
        if not self.enabled:
            raise PermissionError("Cutover operator is disabled")

    @staticmethod
    def _system_runner(args):
        completed = subprocess.run(
            args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=50, check=False)
        return completed.returncode == 0

    @staticmethod
    def _system_mountinfo():
        with open("/proc/self/mountinfo", "r", encoding="utf-8") as source:
            return source.read()

    def _systemctl(self, operation, *names):
        self._require_enabled()
        allowed_operations = {
            "start", "stop", "enable", "disable",
            "daemon-reload", "is-active",
        }
        allowed_names = set(rollout.LEGACY_SERVICES)
        allowed_names.update(rollout.NEW_SERVICES)
        allowed_names.update(rollout.BIND_SERVICES)
        if operation not in allowed_operations:
            raise ValueError("Unauthorized systemctl operation")
        if operation == "daemon-reload":
            if names:
                raise ValueError("Unexpected reload unit")
        elif len(names) != 1 or names[0] not in allowed_names:
            raise ValueError("Unexpected systemd unit")
        if self.runner(["systemctl", operation] + list(names)) is not True:
            raise RuntimeError("Local systemd action did not complete")

    def _active(self, unit):
        self._require_enabled()
        return self.runner(["systemctl", "is-active", "--quiet", unit]) is True

    def _mounts(self):
        return health.mount_entries(self.mount_reader())

    def _old_mounted(self):
        entries = self._mounts()
        return all(entries.get(dst, {}).get("fstype") == "fuse.rclone"
                   for _, _, _, dst in plan.BIND_MAP)

    def legacy_preflight(self):
        self._require_enabled()
        if (os.path.lexists(self.state_path)
                or any(os.path.lexists(os.path.join(self.unit_dir, x))
                       for x in rollout.NEW_SERVICES + rollout.BIND_SERVICES)
                or any(os.path.lexists(path) for path in self.account_confs)):
            return False
        raw, _ = stage._read_file(self.canonical, confidential=True)
        units = {
            name: stage._read_file(os.path.join(self.unit_dir, name))[0]
            for name in rollout.LEGACY_SERVICES
        }
        plan.generate(raw, units)
        # Los targets legacy no deben tener capas superpuestas. El último
        # match de mountinfo no basta si hay dos FUSE sobre la misma ruta.
        raw_mounts = self.mount_reader()
        expected = {dst: 0 for _, _, _, dst in plan.BIND_MAP}
        for line in raw_mounts.splitlines():
            fields = line.partition(" - ")[0].split()
            if len(fields) < 5:
                return False
            if fields[4] in expected:
                expected[fields[4]] += 1
        if set(expected.values()) != {1}:
            return False
        if not self._old_mounted():
            return False
        entries = self._mounts()
        if any(root in entries for root in plan.FUSE_ROOTS):
            return False
        if not all(self._active(unit) for unit in rollout.LEGACY_SERVICES):
            return False
        self.baseline = raw
        self.units = units
        return True

    def playback_still_idle(self):
        self._require_enabled()
        return kodi_idle.is_playback_idle(self.rpc)

    def prepare_durable_rollback(self):
        self._require_enabled()
        if self.baseline is None or self.units is None:
            return False
        self.txn = journal.prepare(self.txn_parent, self.baseline, self.units)
        return journal.phase(self.txn) == "prepared"

    @staticmethod
    def _unsafe_marker():
        return (
            '{"schema":1,"layout":"two-fuse-v1","state":"cutover_started",'
            '"candidate_id":"2026-11-17-two-fuse-v1"}\n'
        ).encode("utf-8")

    @staticmethod
    def _active_marker():
        return (
            '{"schema":1,"layout":"two-fuse-v1","state":"active",'
            '"candidate_id":"2026-11-17-two-fuse-v1"}\n'
        ).encode("utf-8")

    def mark_cutover_started(self):
        self._require_enabled()
        if self.txn is None or journal.phase(self.txn) != "prepared":
            raise ValueError("Missing durable backup")
        # Bloquea el actualizador legacy incluso si Kodi reinicia durante
        # el corte. El estado es inválido para rollout.mode => unsafe.
        atomic.install_exclusive(self.state_path, self._unsafe_marker(), 0o600)
        journal.transition(self.txn, "prepared", "cutover_started")

    def stop_legacy(self):
        self._require_enabled()
        for unit in rollout.LEGACY_SERVICES:
            self._systemctl("stop", unit)

    def legacy_fully_unmounted(self):
        self._require_enabled()
        entries = self._mounts()
        return (all(target not in entries
                    for _, _, _, target in plan.BIND_MAP)
                and not any(self._active(unit)
                            for unit in rollout.LEGACY_SERVICES))

    def install_current_v2(self):
        self._require_enabled()
        if not self.legacy_fully_unmounted() or self.baseline is None:
            raise ValueError("Legacy still active")
        latest, _ = stage._read_file(self.canonical, confidential=True)
        if not conf.same_non_token_settings(self.baseline, latest):
            raise ValueError("Canonical identity changed")
        proposal = plan.generate(latest, self.units)
        self.at_stop = latest
        journal._write_new(os.path.join(self.txn, "canonical-at-stop.conf"),
                           latest)
        journal._sync(self.txn)
        parent = os.path.dirname(self.account_confs[0])
        if os.path.dirname(self.account_confs[1]) != parent:
            raise ValueError("Account config parents differ")
        os.makedirs(parent, mode=0o700, exist_ok=True)
        journal._private_dir(parent)
        self.candidate = proposal
        for i in (0, 1):
            name = "account{}.conf".format(i + 1)
            data, mode = proposal[name]
            path = self.account_confs[i]
            atomic.install_exclusive(path, data, mode)
            self.installed[path] = data
        for name in rollout.NEW_SERVICES + rollout.BIND_SERVICES:
            data, mode = proposal[name]
            path = os.path.join(self.unit_dir, name)
            atomic.install_exclusive(path, data, mode)
            self.installed[path] = data
        self._systemctl("daemon-reload")

    def start_fuse(self):
        self._require_enabled()
        for unit in rollout.NEW_SERVICES:
            self._systemctl("start", unit)
            self.started_roots.add(unit)

    def fuse_ready(self):
        self._require_enabled()
        for _ in range(60):
            entries = self._mounts()
            if all(entries.get(path, {}).get("fstype") == "fuse.rclone"
                   for path in plan.FUSE_ROOTS):
                return True
            time.sleep(0.25)
        return False

    def start_binds(self):
        self._require_enabled()
        for unit in rollout.BIND_SERVICES:
            # Registrar antes del comando: pudo arrancar aunque systemctl
            # expirase. El rollback debe intentar detenerlo.
            self.attempted_binds.add(unit)
            self._systemctl("start", unit)

    @staticmethod
    def _probe_known_media(path):
        """Lectura de 1 byte en subproceso, timeout 15s sin shell.

        Un FUSE de OneDrive bloqueado no debe congelar indefinidamente
        el thread de control de la transición. Solo se reciben códigos
        de estado: ningún dato del fichero se imprime.
        """
        python = shutil.which("python3")
        if not python:
            return False
        probe = (
            "import sys; f=open(sys.argv[1], 'rb'); "
            "sys.exit(0 if f.read(1) else 2)"
        )
        try:
            p = subprocess.run(
                [python, "-c", probe, path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=15, check=False,
            )
            return p.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _known_media_verified(self):
        """Una lectura exacta por OneDrive. No recorre directorios remotos."""
        if len(self.known_media_files) != 2:
            return False
        for index, path in enumerate(self.known_media_files, 1):
            prefixes = (
                "/storage/.mnt/videos/{}/".format(index),
                "/storage/.mnt/tvshows/{}/".format(index),
            )
            if (not isinstance(path, str) or not os.path.isabs(path)
                    or os.path.normpath(path) != path
                    or not path.startswith(prefixes)):
                return False
            if not self._probe_known_media(path):
                return False
        return True

    def complete_health(self):
        self._require_enabled()
        return (health.check_two_fuse_four_bind(self.mount_reader())
                and all(self._active(unit) for unit in (
                    rollout.NEW_SERVICES + rollout.BIND_SERVICES))
                and self._known_media_verified())

    def mark_active(self):
        self._require_enabled()
        if self.txn is None or journal.phase(self.txn) != "cutover_started":
            raise ValueError("Durable phase not ready")
        if not self.complete_health():
            raise ValueError("2 FUSE, 4 bind or known-media read failed")
        for unit in rollout.NEW_SERVICES + rollout.BIND_SERVICES:
            self._systemctl("enable", unit)
        for unit in rollout.LEGACY_SERVICES:
            self._systemctl("disable", unit)
        self._replace_marker(self._unsafe_marker(), self._active_marker())
        journal.transition(self.txn, "cutover_started", "active")

    def _replace_marker(self, expected, new):
        old, generation = stage._read_file(self.state_path, confidential=True)
        if old != expected:
            raise ValueError("Unexpected architecture marker")
        fd, path = tempfile.mkstemp(
            prefix=".rclone-v2-mode-", dir=os.path.dirname(self.state_path))
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb", closefd=False) as dest:
                dest.write(new)
                dest.flush()
            os.fsync(fd)
            now, newer_generation = stage._read_file(
                self.state_path, confidential=True)
            if (now != expected or newer_generation != generation):
                raise ValueError("Architecture marker changed")
            os.replace(path, self.state_path)
            journal._sync(os.path.dirname(self.state_path))
        finally:
            os.close(fd)
            if os.path.exists(path):
                os.unlink(path)

    def stop_binds(self):
        self._require_enabled()
        for unit in reversed(rollout.BIND_SERVICES):
            if (os.path.lexists(os.path.join(self.unit_dir, unit))
                    and (unit in self.attempted_binds or self._active(unit))):
                self._systemctl("stop", unit)

    def stop_fuse(self):
        self._require_enabled()
        for unit in reversed(rollout.NEW_SERVICES):
            if (os.path.lexists(os.path.join(self.unit_dir, unit))
                    and (unit in self.started_roots or self._active(unit))):
                self._systemctl("stop", unit)

    def new_fully_unmounted(self):
        self._require_enabled()
        # FUSE desmontado no implica que el proceso escritor haya muerto.
        # No leer account*.conf para rollback mientras rclone siga activo.
        if any(self._active(unit) for unit in rollout.NEW_SERVICES):
            return False
        entries = self._mounts()
        if any(root in entries for root in plan.FUSE_ROOTS):
            return False
        # No confundir legacy FUSE (fsroot=/) con bind v2 (fsroot=/movies).
        for _, _, folder, target in plan.BIND_MAP:
            entry = entries.get(target)
            if entry is not None and entry["fsroot"].rstrip("/") == "/" + folder:
                return False
        return True

    def _rewrite_canonical_if_stable(self, baseline, new):
        """Nunca reemplazar rclone.conf mientras haya escritores externos.

        rclone NO respeta flock del addon: ni comparar mtime/inode antes de
        os.replace puede impedir una renovación simultánea de Google Drive.
        El candidato reconciliado queda en journal PRIVADO para una fase
        posterior con todos los escritores efectivamente detenidos.
        """
        self._require_enabled()
        current, _generation = stage._read_file(self.canonical,
                                                confidential=True)
        if current != baseline:
            raise ValueError("Canonical changed during rollback")
        if current == new:
            return
        if self.txn is None or journal.phase(self.txn) not in (
                "cutover_started", "active", "rollback_required"):
            raise ValueError("Missing rollback journal")
        # No reemplaza ni reescribe la configuración compartida. Evita
        # perder tokens Google Drive por un cambio concurrente sin CAS.
        journal._write_new(
            os.path.join(self.txn, "canonical-recovery-candidate.conf"), new)
        journal._sync(self.txn)
        raise RuntimeError(
            "Shared canonical not safely quiesced; manual recovery required")

    def reconcile_and_restore_legacy(self):
        self._require_enabled()
        if self.txn is None:
            raise ValueError("No rollback journal")
        phase = journal.phase(self.txn)
        if phase in ("cutover_started", "active"):
            journal.transition(self.txn, phase, "rollback_required")
        current, _ = stage._read_file(self.canonical, confidential=True)
        if self.at_stop is not None:
            snapshots = []
            for index, path in enumerate(self.account_confs):
                if os.path.lexists(path):
                    raw = stage._read_file(path, confidential=True)[0]
                elif self.candidate is not None and not self.started_roots:
                    raw = self.candidate["account{}.conf".format(index+1)][0]
                else:
                    raise ValueError("Missing refreshed account state")
                snapshots.append(raw)
            new = oauth.reconcile_canonical_for_rollback(
                self.at_stop, current, snapshots[0], snapshots[1])
            self._rewrite_canonical_if_stable(current, new)
        elif self.baseline is not None:
            # Falla antes de instalar v2: no se sobrescriben tokens canónicos.
            if not conf.same_non_token_settings(self.baseline, current):
                raise ValueError("Canonical changed before install")
        else:
            raise ValueError("Missing baseline")

    def start_legacy(self):
        self._require_enabled()
        for unit in rollout.NEW_SERVICES + rollout.BIND_SERVICES:
            if os.path.lexists(os.path.join(self.unit_dir, unit)):
                self._systemctl("disable", unit)
        for unit in rollout.LEGACY_SERVICES:
            self._systemctl("enable", unit)
            self._systemctl("start", unit)

    def legacy_healthy(self):
        self._require_enabled()
        return (self._old_mounted()
                and all(self._active(unit) for unit in rollout.LEGACY_SERVICES))

    def mark_legacy_restored(self):
        self._require_enabled()
        if not self.new_fully_unmounted() or not self.legacy_healthy():
            raise ValueError("Unsafe rollback state")
        for path, content in reversed(tuple(self.installed.items())):
            if path in self.account_confs:
                # Account secrets pueden haberse renovado: ya conciliados.
                content = stage._read_file(path, confidential=True)[0]
            atomic.remove_if_identical(path, content)
        self._systemctl("daemon-reload")
        if os.path.lexists(self.state_path):
            existing, _ = stage._read_file(
                self.state_path, confidential=True)
            if existing not in (self._unsafe_marker(), self._active_marker()):
                raise ValueError("Unknown marker cannot be removed")
            os.unlink(self.state_path)
            journal._sync(os.path.dirname(self.state_path))
        phase = journal.phase(self.txn)
        if phase == "rollback_required":
            journal.transition(self.txn, "rollback_required",
                               "legacy_restored")
        elif phase != "prepared":
            raise ValueError("Inconsistent restored phase")


def execute_with_local_lock(adapter, *, authorized=False,
                            verified_rollback=False):
    """No bootstrap live. Requiere callback Kodi; ambos flags default NO."""
    if authorized is not True or not adapter.enabled:
        return "BLOCKED_NOT_AUTHORIZED"
    if verified_rollback is not True:
        return "BLOCKED_ROLLBACK_NOT_READY"
    try:
        with journal.locked(adapter.txn_parent):
            return engine.run(
                adapter, release_authorized=True,
                playback_idle=kodi_idle.is_playback_idle(adapter.rpc),
                rollback_ready=True)
    except (OSError, ValueError, BlockingIOError):
        return "MANUAL_RECOVERY_REQUIRED"
