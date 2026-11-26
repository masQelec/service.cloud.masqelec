# -*- coding: utf-8 -*-
"""Prueba de interfaces reales desde Kodi, sin actualizar TVH."""

import json
import os
import re
import sys

from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parents[1]),
)


def probe():

    import xbmc

    from lib import cloud_version_routes as routes
    from lib import tvheadend_activity as activity
    from lib import tvheadend_boot as boot
    from lib import tvheadend_health as health
    from lib import tvheadend_kodi as kodi
    from lib import tvheadend_platform as platform
    from lib import tvheadend_transaction as tx
    from lib import tvheadend_update_policy as policy
    from lib.update_pvr import _tvh_api_get_json

    branch, base = routes.route_from_kodi_rpc(
        xbmc.executeJSONRPC
    )

    assert branch == "21"

    device = platform.detect()

    controller = kodi.KodiController(
        xbmc.executeJSONRPC,
        xbmc.executebuiltin,
    )

    state = controller.state()

    identity = tx.identity(
        boot.ACTIVE_ADDON
    )

    assert state.enabled
    assert state.version == identity["version"]

    ok, code, data, _ = _tvh_api_get_json(
        "status/activity",
        timeout_s=5,
    )

    assert ok is True
    assert code == 200
    assert isinstance(data, dict)

    tvh_activity = activity.evaluate_tvh_activity(
        data
    )

    assert tvh_activity.status != (
        "DEFERRED_ACTIVITY_UNKNOWN"
    )

    combined_activity = activity.check_activity(
        xbmc.executeJSONRPC,
        _tvh_api_get_json,
    )

    assert combined_activity.status != (
        "DEFERRED_ACTIVITY_UNKNOWN"
    )

    verified = health.verify_running(
        identity["binary_sha256"],
        _tvh_api_get_json,
    )

    assert verified["health"] == "PASS"

    return {
        "result": "PASS",
        "branch": branch,
        "base": base,
        "target": device.target,
        "coreelec_version": device.coreelec_version,
        "coreelec_build": device.coreelec_build,
        "installed_version": identity["version"],
        "binary_sha256": identity["binary_sha256"],
        "kodi_enabled": state.enabled,
        "tvh_activity": tvh_activity.status,
        "combined_activity": combined_activity.status,
        "policy_present": policy.inspect_policy(),
        "service_health": verified["health"],
        "installation_performed": False,
    }


def main():

    assert len(sys.argv) == 2

    report = Path(sys.argv[1])

    assert report.is_absolute()
    assert report.name == "runtime-report.json"
    assert report.parent.resolve() == report.parent
    assert report.parent.parent == Path(
        "/storage/masqelec-backups"
    )

    try:

        result = probe()

    except Exception as error:

        result = {
            "result": "FAIL",
            "error_type": type(error).__name__,
        }

        if re.fullmatch(
            r"[A-Z0-9_]+",
            str(error),
        ):

            result["error_code"] = str(error)

    temporary = report.with_suffix(".tmp")

    fd = os.open(
        temporary,
        os.O_CREAT | os.O_EXCL | os.O_WRONLY,
        0o600,
    )

    with os.fdopen(fd, "w") as handle:

        json.dump(result, handle, indent=2)

        handle.flush()

        os.fsync(handle.fileno())

    os.replace(temporary, report)


if __name__ == "__main__":
    main()
