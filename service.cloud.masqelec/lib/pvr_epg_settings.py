# -*- coding: utf-8 -*-
"""Configuracion XMLTV mediante la interfaz nativa Kodi."""

ADDON_ID = "service.tvheadend43"

EPG_URL = (
    "https://raw.githubusercontent.com/"
    "masQelec/epg/main/guide.xml"
)

DESIRED_SETTINGS = (
    ("XMLTV_LOCATION_WEB", EPG_URL),
    ("XMLTV_TYPE", "WEB"),
)


class EpgSettingsError(RuntimeError):
    pass


def inspect_settings(addon_factory=None):

    if addon_factory is None:
        import xbmcaddon
        addon_factory = xbmcaddon.Addon

    addon = addon_factory(ADDON_ID)

    return {
        key: addon.getSetting(key)
        for key, _ in DESIRED_SETTINGS
    }


def ensure_settings(
    addon_factory=None,
    *,
    authorized=False,
):
    """Aplica solamente diferencias y verifica cada escritura.

    La URL se establece antes de seleccionar el tipo WEB.
    No modifica directamente settings.xml.
    No solicita reinicios ni recargas de la guia.
    """

    if authorized is not True:
        return "NOT_AUTHORIZED"

    if addon_factory is None:
        import xbmcaddon
        addon_factory = xbmcaddon.Addon

    addon = addon_factory(ADDON_ID)

    changed = False

    for key, desired in DESIRED_SETTINGS:

        if addon.getSetting(key) == desired:
            continue

        addon.setSetting(key, desired)

        fresh = addon_factory(ADDON_ID)

        if fresh.getSetting(key) != desired:

            raise EpgSettingsError(
                "XMLTV_SETTING_NOT_CONFIRMED:" + key
            )

        addon = fresh

        changed = True

    observed = inspect_settings(addon_factory)

    if observed != dict(DESIRED_SETTINGS):

        raise EpgSettingsError(
            "XMLTV_SETTINGS_MISMATCH"
        )

    return "UPDATED" if changed else "UNCHANGED"
