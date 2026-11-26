# -*- coding: utf-8 -*-
"""Control estricto de Tvheadend mediante API nativa Kodi.

Sin dependencias directas de Kodi, SQLite o systemd.
"""

import json
import time

from dataclasses import dataclass

from lib.tvheadend_manifest import ADDON_ID
from lib.tvheadend_version import parse_version


class KodiAddonError(ValueError):
    """Operacion Kodi no confirmada."""


@dataclass(frozen=True)
class AddonState:
    version: str
    enabled: bool


class KodiController:

    def __init__(
        self,
        rpc_call,
        execute_builtin,
        wait=None,
    ):

        self._rpc_call = rpc_call
        self._builtin = execute_builtin
        self._wait = wait or self._default_wait

    @staticmethod
    def _default_wait(seconds):
        time.sleep(seconds)
        return False

    def _rpc(self, method, params):

        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": method,
            "params": params,
        }

        try:

            data = json.loads(
                self._rpc_call(
                    json.dumps(request)
                )
            )

        except Exception:
            raise KodiAddonError(
                "KODI_RPC_UNAVAILABLE"
            ) from None

        if not (
            isinstance(data, dict)
            and data.get("jsonrpc") == "2.0"
            and type(data.get("id")) is int
            and data["id"] == 1
            and "error" not in data
            and "result" in data
        ):
            raise KodiAddonError(
                "KODI_RPC_INVALID_RESPONSE"
            )

        return data["result"]

    def state(self):

        result = self._rpc(
            "Addons.GetAddonDetails",
            {
                "addonid": ADDON_ID,
                "properties": [
                    "version",
                    "enabled",
                ],
            },
        )

        if not isinstance(result, dict):
            raise KodiAddonError(
                "KODI_INVALID_ADDON_STATE"
            )

        addon = result.get("addon")

        if not (
            isinstance(addon, dict)
            and addon.get("addonid") == ADDON_ID
            and type(addon.get("enabled")) is bool
        ):
            raise KodiAddonError(
                "KODI_INVALID_ADDON_STATE"
            )

        version = addon.get("version")

        try:
            parse_version(version)

        except ValueError:
            raise KodiAddonError(
                "KODI_INVALID_ADDON_VERSION"
            ) from None

        return AddonState(
            version=version,
            enabled=addon["enabled"],
        )

    def wait_state(
        self,
        expected_version,
        enabled,
        attempts=20,
    ):

        parse_version(expected_version)

        if (
            type(enabled) is not bool
            or type(attempts) is not int
            or not 1 <= attempts <= 120
        ):
            raise KodiAddonError(
                "INVALID_WAIT_POLICY"
            )

        expected = AddonState(
            expected_version, enabled
        )

        for index in range(attempts):

            try:

                observed = self.state()

                if observed == expected:
                    return observed

            except KodiAddonError:
                pass

            if index + 1 < attempts:

                if self._wait(1):
                    raise KodiAddonError(
                        "KODI_WAIT_ABORTED"
                    )

        raise KodiAddonError(
            "KODI_STATE_NOT_CONFIRMED"
        )

    def set_enabled(
        self,
        enabled,
        expected_version,
    ):

        if type(enabled) is not bool:
            raise KodiAddonError(
                "INVALID_ENABLED_STATE"
            )

        before = self.state()

        if before.version != expected_version:
            raise KodiAddonError(
                "KODI_VERSION_CHANGED"
            )

        if before.enabled == enabled:
            return before

        result = self._rpc(
            "Addons.SetAddonEnabled",
            {
                "addonid": ADDON_ID,
                "enabled": enabled,
            },
        )

        if result != "OK":
            raise KodiAddonError(
                "KODI_ENABLE_NOT_ACKNOWLEDGED"
            )

        return self.wait_state(
            expected_version,
            enabled,
        )

    def rescan_disabled(
        self,
        expected_version,
    ):

        parse_version(expected_version)

        before = self.state()

        if before.enabled:
            raise KodiAddonError(
                "KODI_ADDON_MUST_BE_DISABLED"
            )

        try:

            self._builtin(
                "UpdateLocalAddons",
                True,
            )

        except Exception:
            raise KodiAddonError(
                "KODI_RESCAN_FAILED"
            ) from None

        return self.wait_state(
            expected_version,
            False,
        )
