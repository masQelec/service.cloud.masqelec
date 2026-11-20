# -*- coding: utf-8 -*-
"""P0-C: modelo PURO de coordinación OAuth MASTER/CLIENTES (solo laboratorio).

No interactúa con rclone, systemd, red, GitHub ni tokens. Un informe de
"quiescencia" es una AFIRMACIÓN del test; no una prueba real de que Microsoft
no reciba renovaciones. Cualquier estado positivo termina en _lab_only.
"""
import re
import secrets

_ID = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}\Z")
_COHORT = re.compile(r"[a-f0-9]{32}\Z")
_MAX_DEVICES = 128
_MAX_TTL = 300


class FleetWindow:
    """Ventana efímera sin autorización operativa; repr oculta miembros."""

    __slots__ = ("_account", "_members", "_revision", "_cohort", "_nonce",
                 "_started", "_deadline", "_acks", "_aborted")

    def __init__(self, account, members, revision, cohort, started, ttl):
        self._account = account
        self._members = members
        self._revision = revision
        self._cohort = cohort
        self._nonce = secrets.token_hex(16)
        self._started = started
        self._deadline = started + ttl
        self._acks = {}
        self._aborted = False

    def __repr__(self):
        return "<FleetWindow redacted / lab-only>"

    @property
    def challenge(self):
        """Valor efímero SOLO para simular reports atados a esta ventana."""
        return self._nonce


def _validate_members(members):
    """Tupla (identificador, modo, online, epoch_escritor, cuentas).

    Cuentas=(0,), (1,) o (0,1). Los epochs solo tienen semántica si
    TODOS los procesos y dispositivos escriben exclusivamente por el
    coordinador, cosa que NO ocurre en masQelec legacy.
    """
    if type(members) is not tuple or not 0 < len(members) <= _MAX_DEVICES:
        raise ValueError("Inventario de flota inválido")
    seen = set()
    normalized = []
    for item in members:
        if type(item) is not tuple or len(item) != 5:
            raise ValueError("Registro de equipo inválido")
        device_id, mode, online, epoch, accounts = item
        if (not isinstance(device_id, str) or
                not _ID.fullmatch(device_id) or device_id in seen):
            raise ValueError("Identidad de equipo inválida o duplicada")
        if mode not in ("cooperative", "legacy", "unknown"):
            raise ValueError("Modo de escritor inválido")
        if type(online) is not bool or type(epoch) is not int or epoch < 0:
            raise ValueError("Estado o generación inválida")
        if (type(accounts) is not tuple or not accounts or
                len(accounts) > 2 or
                any(type(a) is not int or a not in (0, 1)
                    for a in accounts) or
                len(set(accounts)) != len(accounts)):
            raise ValueError("Cuentas del dispositivo inválidas")
        seen.add(device_id)
        normalized.append((device_id, mode, online, epoch,
                           tuple(sorted(accounts))))
    return tuple(sorted(normalized))


def _validate_meta(account, revision, cohort, now, ttl):
    if type(account) is not int or account not in (0, 1):
        raise ValueError("Cuenta no admitida")
    if type(revision) is not int or revision < 0:
        raise ValueError("Revisión de inventario no válida")
    if not isinstance(cohort, str) or not _COHORT.fullmatch(cohort):
        raise ValueError("Identificador de operación no válido")
    if type(now) is not int or now < 0:
        raise ValueError("Tiempo monotónico de coordinador inválido")
    if type(ttl) is not int or not 1 <= ttl <= _MAX_TTL:
        raise ValueError("Ventana de prueba fuera de límites")


def begin_freeze(account, inventory, revision, cohort, now, *,
                 inventory_authoritative=False, fleet_complete=False,
                 ttl=60):
    """Abre una ventana SOLO si la prueba simula inventario completo.

    flags=True son declaraciones de un test; no aportan autenticación de
    equipos ni exclusión de rclone. No usar esta salida para un PUT.
    """
    if inventory_authoritative is not True or fleet_complete is not True:
        return {"status": "blocked_inventory_untrusted", "window": None}
    _validate_meta(account, revision, cohort, now, ttl)
    members = _validate_members(inventory)
    scope = [item for item in members if account in item[4]]
    if not scope:
        return {"status": "blocked_no_writers_in_scope", "window": None}
    if any(item[1] == "legacy" for item in scope):
        return {"status": "blocked_legacy_writers", "window": None}
    if any(item[1] == "unknown" for item in scope):
        return {"status": "blocked_unknown_writer", "window": None}
    if any(item[2] is not True for item in scope):
        return {"status": "blocked_offline_member", "window": None}
    return {
        "status": "awaiting_all_acks_lab_only",
        "window": FleetWindow(account, members, revision, cohort, now, ttl),
    }


def abort_freeze(window):
    """Un aborto no desbloquea ningún writer real (no existe control live)."""
    if not isinstance(window, FleetWindow):
        return "blocked_invalid_window"
    window._aborted = True
    window._acks.clear()
    return "aborted_lab_only"


def acknowledge_quiescence(window, device_id, challenge, writer_epoch, now,
                           *, report_authenticated=False,
                           mounts_stopped=False, refresh_path_fenced=False):
    """Recibo sintético: ningún booleano constituye evidencia criptográfica.

    Un ack fuera del contexto cohorte/challenge o con generación stale no
    puede completar la barrera; no se aceptan "leases" de un equipo ajeno.
    """
    if not isinstance(window, FleetWindow):
        return "blocked_invalid_window"
    if window._aborted:
        return "blocked_aborted"
    if type(now) is not int or now < window._started:
        return "blocked_invalid_clock"
    if now >= window._deadline:
        return "blocked_expired"
    if challenge != window._nonce:
        return "blocked_stale_challenge"
    members = {item[0]: item for item in window._members
               if window._account in item[4]}
    if device_id not in members:
        return "blocked_unknown_member"
    member = members[device_id]
    if type(writer_epoch) is not int or writer_epoch != member[3]:
        return "blocked_writer_changed"
    if (report_authenticated is not True or
            mounts_stopped is not True or
            refresh_path_fenced is not True):
        return "blocked_writer_not_quiescent"
    existing = window._acks.get(device_id)
    if existing is not None:
        return "duplicate_ack_lab_only" if existing == writer_epoch else (
            "blocked_conflicting_ack")
    window._acks[device_id] = writer_epoch
    return "ack_recorded_lab_only"


def assess_freeze(window, current_inventory, revision, now, *,
                  inventory_authoritative=False, fleet_complete=False):
    """Sin prueba de todo el parque y todos los escritores: fail closed."""
    if not isinstance(window, FleetWindow):
        return "blocked_invalid_window"
    if window._aborted:
        return "blocked_aborted"
    if inventory_authoritative is not True or fleet_complete is not True:
        return "blocked_inventory_untrusted"
    if type(now) is not int or now < window._started:
        return "blocked_invalid_clock"
    if now >= window._deadline:
        return "blocked_expired"
    if type(revision) is not int or revision != window._revision:
        return "blocked_inventory_revision_changed"
    try:
        current = _validate_members(current_inventory)
    except ValueError:
        return "blocked_invalid_inventory"
    baseline = window._members
    if {x[0] for x in current} != {x[0] for x in baseline}:
        return "blocked_membership_changed"
    bmap = {item[0]: item for item in baseline}
    for member in current:
        initial = bmap[member[0]]
        if member[1] != initial[1] or member[4] != initial[4]:
            return "blocked_membership_changed"
        if window._account in member[4] and member[2] is not True:
            return "blocked_offline_member"
        if member[3] != initial[3]:
            return "blocked_writer_changed"
    scope = [m[0] for m in baseline if window._account in m[4]]
    if any(id_ not in window._acks for id_ in scope):
        return "blocked_missing_ack"
    return "quiescent_lab_only"


def assess_canonical_pair(first, second, inventory, revision, now, *,
                          inventory_authoritative=False, fleet_complete=False):
    """El MQC2 global contiene AMBAS OneDrive; exige ambos fences.

    No devuelve permiso operativo. Se rechazan ventanas incoherentes o
    generaciones del registro distintos, incluso con dos acks completos.
    """
    if (not isinstance(first, FleetWindow) or
            not isinstance(second, FleetWindow) or first is second or
            first._account != 0 or second._account != 1 or
            first._revision != second._revision or
            first._cohort != second._cohort or
            first._members != second._members):
        return "blocked_pair_inconsistent"
    params = dict(inventory_authoritative=inventory_authoritative,
                  fleet_complete=fleet_complete)
    a = assess_freeze(first, inventory, revision, now, **params)
    b = assess_freeze(second, inventory, revision, now, **params)
    if a != "quiescent_lab_only":
        return a
    if b != "quiescent_lab_only":
        return b
    return "both_accounts_quiescent_lab_only"
