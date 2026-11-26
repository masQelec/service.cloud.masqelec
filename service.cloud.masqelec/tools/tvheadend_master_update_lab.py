# -*- coding: utf-8 -*-
"""Validacion real NG en MASTER.

Manifiesto y paquete locales.
Sin publicacion remota.
Interfaces Kodi, HTTP y systemd reales.
"""

import hashlib
import json
import os
import sqlite3
import sys
import traceback

from contextlib import closing, contextmanager
from dataclasses import replace
from pathlib import Path


ADDON = Path(
    "/storage/.kodi/addons/service.cloud.masqelec"
)

sys.path.insert(0, str(ADDON))

OLD_VERSION = "21.2.7"
NEW_VERSION = "21.2.8"

OLD_SHA = (
    "2c47d2b41eefbcb638ff2defa5f78822"
    "f0f825921445fa6d444cb0e0efb41711"
)

NEW_SHA = (
    "6c87ff5c3de2023373b9e36571f5de984"
    "8c074cddaafb995bfbd00089712cc80"
)

ZIP_SHA = (
    "282e8169c51c8bb30a1ca0e1b47ec4dde"
    "5ecd91cc122092d6617bb6efbde45e3"
)

EXPECTED_BUILD = (
    "21.2.5-Omega_devel_20250919152246"
)

TV_DATABASE = Path(
    "/storage/.kodi/userdata/Database/TV46.db"
)


def require(condition, code):

    if not condition:
        raise RuntimeError(code)


def sha256(path):

    digest = hashlib.sha256()

    with Path(path).open("rb") as handle:

        while True:

            block = handle.read(262144)

            if not block:
                break

            digest.update(block)

    return digest.hexdigest()


def pvr_snapshot():

    require(
        TV_DATABASE.is_file(),
        "PVR_DATABASE_MISSING",
    )

    with closing(sqlite3.connect(
        TV_DATABASE.as_uri() + "?mode=ro",
        uri=True,
        timeout=5,
    )) as conn:

        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")

        require(
            conn.execute(
                "PRAGMA quick_check"
            ).fetchall() == [("ok",)],
            "PVR_DATABASE_INTEGRITY_FAILED",
        )

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(channels)"
            )
        }

        clients = columns.intersection({
            "idClient",
            "iClientId",
        })

        require(
            len(clients) == 1,
            "UNEXPECTED_PVR_CLIENT_COLUMN",
        )

        require(
            {"idChannel", "iUniqueId"}.issubset(columns),
            "UNEXPECTED_PVR_CHANNEL_SCHEMA",
        )

        client_column = clients.pop()

        channels = conn.execute(
            f'SELECT idChannel, "{client_column}", iUniqueId '
            'FROM channels ORDER BY idChannel'
        ).fetchall()

        require(
            bool(channels),
            "PVR_CHANNELS_EMPTY",
        )

        groups = conn.execute("""
            SELECT COUNT(*) FROM channelgroups
        """).fetchone()[0]

        mappings = conn.execute("""
            SELECT COUNT(*)
            FROM map_channelgroups_channels
        """).fetchone()[0]

        conn.execute("ROLLBACK")

    return {
        "channels": len(channels),
        "groups": groups,
        "mappings": mappings,
        "channel_identity_sha256": hashlib.sha256(
            json.dumps(channels).encode("utf-8")
        ).hexdigest(),
    }


def execute(stage, report):

    import xbmc

    from lib import cloud_version_routes as routes
    from lib import tvheadend_activity as activity
    from lib import tvheadend_boot as boot
    from lib import tvheadend_boot_policy as policy
    from lib import tvheadend_health as health
    from lib import tvheadend_kodi as kodi
    from lib import tvheadend_manifest as manifest
    from lib import tvheadend_package as package
    from lib import tvheadend_platform as platform
    from lib import tvheadend_runtime as runtime
    from lib import tvheadend_transaction as tx
    from lib import tvheadend_update_service as service
    from lib import tvheadend_version as version
    from lib.update_pvr import _tvh_api_get_json

    branch, base = routes.route_from_kodi_rpc(
        xbmc.executeJSONRPC
    )

    require(
        branch == "21",
        "UNEXPECTED_KODI_BRANCH",
    )

    device = platform.detect()

    require(
        device.target == "Amlogic-ng.arm"
        and device.coreelec_version == "21.2.5"
        and device.coreelec_build == EXPECTED_BUILD,
        "UNEXPECTED_MASTER_PLATFORM",
    )

    require(
        runtime.protection_ready(),
        "SYSTEMD_PROTECTION_NOT_READY",
    )

    require(
        policy.policy_ready(),
        "UPDATE_POLICY_NOT_READY",
    )

    controller = kodi.KodiController(
        xbmc.executeJSONRPC,
        xbmc.executebuiltin,
    )

    state = controller.state()

    require(
        state.enabled
        and state.version == OLD_VERSION,
        "UNEXPECTED_KODI_ADDON_STATE",
    )

    old = tx.identity(boot.ACTIVE_ADDON)

    require(
        old["version"] == OLD_VERSION
        and old["binary_sha256"] == OLD_SHA,
        "UNEXPECTED_OLD_BINARY",
    )

    require(
        activity.check_activity(
            xbmc.executeJSONRPC,
            _tvh_api_get_json,
        ).allowed,
        "TVH_NOT_IDLE",
    )

    require(
        health.verify_running(
            OLD_SHA,
            _tvh_api_get_json,
        )["health"] == "PASS",
        "ORIGINAL_SERVICE_UNHEALTHY",
    )

    require(
        not boot.TRANSACTION_ROOT.exists(),
        "UNEXPECTED_TRANSACTION_ROOT",
    )

    grabber = (
        boot.ACTIVE_ADDON
        / "bin/tv_grab_file"
    )

    grabber_before = sha256(grabber)

    report["before"] = {
        "addon": old,
        "grabber_sha256": grabber_before,
        "pvr": pvr_snapshot(),
    }

    candidate = stage / "manifest-candidate.json"

    original = manifest.parse_manifest(
        candidate.read_bytes(),
        21,
    )

    matching = [
        entry for entry in original.packages
        if entry.target == device.target
    ]

    require(
        len(matching) == 1,
        "AMBIGUOUS_PACKAGE",
    )

    entry = matching[0]

    require(
        entry.version == NEW_VERSION
        and entry.sha256 == ZIP_SHA
        and not entry.validated_builds,
        "UNEXPECTED_CANDIDATE_MANIFEST",
    )

    # Autorizacion limitada a esta ejecucion
    # y a este build exacto del MASTER.

    lab_entry = replace(
        entry,
        validated_builds=(
            (
                device.coreelec_version,
                device.coreelec_build,
            ),
        ),
    )

    distribution = replace(
        original,
        packages=(lab_entry,),
    )

    selected = version.decide_update(
        distribution,
        device,
        OLD_VERSION,
    )

    require(
        selected.status == "UPDATE_AVAILABLE",
        "LAB_PACKAGE_NOT_SELECTED",
    )

    zip_path = stage / "service.tvheadend43-21.2.8.zip"

    require(
        sha256(zip_path) == ZIP_SHA,
        "PACKAGE_SHA256_MISMATCH",
    )

    package.validate_zip(
        zip_path,
        lab_entry,
        device,
    )

    report["package_validation"] = "PASS"

    @contextmanager
    def local_stage(
        distribution,
        device,
        installed_version,
        branch,
        base,
        staging_parent,
        **kwargs,
    ):

        decision = version.decide_update(
            distribution,
            device,
            installed_version,
        )

        require(
            decision.status == "UPDATE_AVAILABLE"
            and decision.package == lab_entry,
            "UNEXPECTED_LOCAL_STAGE_DECISION",
        )

        package.validate_zip(
            zip_path,
            decision.package,
            device,
        )

        yield decision, zip_path

    real_run_cycle = service.run_cycle

    def lab_run_cycle(*args, **kwargs):

        kwargs["fetch_manifest"] = (
            lambda *a, **k: distribution
        )

        kwargs["stage_package"] = local_stage

        return real_run_cycle(*args, **kwargs)

    # Solo se sustituye el transporte.
    # El coordinador, la transaccion y la recuperacion
    # son los reales.

    service.run_cycle = lab_run_cycle

    try:

        outcome = runtime.run(
            branch=branch,
            base=base,
            authorized=True,
            install_protection=False,
        )

    finally:

        service.run_cycle = real_run_cycle

    report["outcome"] = outcome

    report["manifest_unchanged"] = (
        candidate.read_bytes()
        == original_manifest_bytes
    )

    require(
        report["manifest_unchanged"],
        "MANIFEST_CHANGED",
    )

    monitor = xbmc.Monitor()

    monitor.waitForAbort(15)

    current = tx.identity(boot.ACTIVE_ADDON)

    report["after"] = {
        "addon": current,
        "grabber_sha256": sha256(grabber),
        "pvr": pvr_snapshot(),
        "policy_ready": policy.policy_ready(),
        "kodi_enabled": controller.state().enabled,
    }

    expected_version, expected_sha = (
        (NEW_VERSION, NEW_SHA)
        if outcome == "UPDATED"
        else (OLD_VERSION, OLD_SHA)
    )

    report["service_health"] = (
        health.verify_running(
            expected_sha,
            _tvh_api_get_json,
        )["health"]
    )

    require(
        current["version"] == expected_version
        and current["binary_sha256"] == expected_sha,
        "FINAL_BINARY_MISMATCH",
    )

    require(
        controller.state().version
        == expected_version,
        "KODI_VERSION_MISMATCH",
    )

    require(
        report["after"]["kodi_enabled"],
        "KODI_ADDON_NOT_ENABLED",
    )

    import zipfile
    import hashlib

    with zipfile.ZipFile(zip_path) as archive:

        native_grabber = archive.read(
            "service.tvheadend43/bin/tv_grab_file"
        )

    require(
        report["after"]["grabber_sha256"]
        == hashlib.sha256(native_grabber).hexdigest(),
        "NATIVE_GRABBER_MISMATCH",
    )

    require(
        report["after"]["policy_ready"],
        "UPDATE_POLICY_LOST",
    )

    require(
        report["service_health"] == "PASS",
        "FINAL_SERVICE_UNHEALTHY",
    )

    report["channel_identity_preserved"] = (
        report["before"]["pvr"][
            "channel_identity_sha256"
        ]
        == report["after"]["pvr"][
            "channel_identity_sha256"
        ]
    )

    report["group_counts_preserved"] = (
        report["before"]["pvr"]["groups"]
        == report["after"]["pvr"]["groups"]
        and report["before"]["pvr"]["mappings"]
        == report["after"]["pvr"]["mappings"]
    )

    report["transaction_pending"] = (
        boot.TRANSACTION_ROOT.exists()
    )

    require(
        not report["transaction_pending"],
        "TRANSACTION_NOT_ARCHIVED",
    )

    require(
        outcome == "UPDATED",
        "UPDATE_NOT_COMPLETED",
    )

    require(
        report["channel_identity_preserved"],
        "PVR_CHANNEL_IDENTITIES_CHANGED",
    )

    require(
        report["group_counts_preserved"],
        "PVR_GROUP_COUNTS_CHANGED",
    )

    report["result"] = "PASS"


def main():

    global original_manifest_bytes

    require(
        len(sys.argv) == 2,
        "INVALID_ARGUMENTS",
    )

    stage = Path(sys.argv[1])

    require(
        stage.resolve() == stage
        and stage.parent == Path(
            "/storage/masqelec-backups"
        )
        and stage.name.startswith("PVR-03I8B."),
        "UNSAFE_LAB_STAGE",
    )

    require(
        stage.stat().st_uid == 0
        and not stage.stat().st_mode & 0o077,
        "UNSAFE_LAB_PERMISSIONS",
    )

    original_manifest_bytes = (
        stage / "manifest-candidate.json"
    ).read_bytes()

    report = {
        "result": "FAIL",
        "role": "MASTER_LAB",
        "transport": "LOCAL_PACKAGE",
        "production_publication": False,
    }

    try:

        execute(stage, report)

    except Exception as error:

        report["result"] = "FAIL"

        report["error_type"] = (
            type(error).__name__
        )

        if isinstance(error, sqlite3.Error):

            report["sqlite_error"] = str(error)

            report["sqlite_error_name"] = getattr(
                error,
                "sqlite_errorname",
                None,
            )

        message = str(error)

        if (
            message
            and message.isascii()
            and all(
                char.isupper()
                or char.isdigit()
                or char == "_"
                for char in message
            )
        ):

            report["error_code"] = message

        report["trace"] = [
            {
                "file": Path(frame.filename).name,
                "line": frame.lineno,
                "function": frame.name,
            }
            for frame in traceback.extract_tb(
                error.__traceback__
            )
        ]

    temporary = stage / "update-report.tmp"
    destination = stage / "update-report.json"

    fd = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    with os.fdopen(fd, "w") as handle:

        json.dump(report, handle, indent=2)

        handle.flush()

        os.fsync(handle.fileno())

    os.replace(temporary, destination)


if __name__ == "__main__":
    main()
