# -*- coding: utf-8 -*-
"""Configuracion idempotente mediante la API nativa TVH."""

import json
import re

from pathlib import PurePosixPath

from lib.pvr_http import (
    _tvh_api_get_json,
    _tvh_api_post_form,
)


USER_AGENT = "samsung-agent/1.1"

XMLTV_CLASS = "epggrab_mod_int_xmltv"

UUID_PATTERN = re.compile(r"[0-9a-f]{32}")


class ConfigError(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise ConfigError(code)


def entries(api_get, endpoint, query=None):

    ok, code, data, _ = api_get(
        endpoint,
        query=query,
        timeout_s=10,
    )

    require(
        ok is True
        and code == 200
        and isinstance(data, dict)
        and isinstance(data.get("entries"), list),
        "API_LOAD_FAILED:" + endpoint,
    )

    return data["entries"]


def single_node(api_get, endpoint, query=None):

    rows = entries(
        api_get, endpoint, query
    )

    require(
        len(rows) == 1
        and isinstance(rows[0], dict),
        "INVALID_NODE:" + endpoint,
    )

    return rows[0]


def properties(node):

    result = {}

    params = node.get("params")

    require(
        isinstance(params, list),
        "INVALID_NODE_PROPERTIES",
    )

    for prop in params:

        require(
            isinstance(prop, dict)
            and isinstance(prop.get("id"), str)
            and prop["id"] not in result,
            "INVALID_PROPERTY",
        )

        result[prop["id"]] = prop

    return result


def property_value(props, key, expected_type):

    require(
        key in props
        and "value" in props[key],
        "PROPERTY_MISSING:" + key,
    )

    value = props[key]["value"]

    require(
        type(value) is expected_type,
        "PROPERTY_TYPE_MISMATCH:" + key,
    )

    return value


def load_module(api_get, uuid):

    node = single_node(
        api_get,
        "idnode/load",
        {"uuid": uuid, "meta": 1},
    )

    require(
        node.get("uuid") == uuid,
        "MODULE_IDENTITY_MISMATCH",
    )

    return node


def find_xmltv_module(api_get):

    rows = entries(
        api_get,
        "epggrab/module/list",
    )

    require(
        0 < len(rows) <= 128,
        "INVALID_MODULE_COUNT",
    )

    candidates = []
    seen = set()

    for row in rows:

        require(
            isinstance(row, dict),
            "INVALID_MODULE_ENTRY",
        )

        uuid = row.get("uuid")

        require(
            isinstance(uuid, str)
            and UUID_PATTERN.fullmatch(uuid)
            and uuid not in seen,
            "INVALID_MODULE_UUID",
        )

        seen.add(uuid)

        node = load_module(
            api_get, uuid
        )

        if node.get("class") != XMLTV_CLASS:
            continue

        props = properties(node)

        path = property_value(
            props, "path", str
        )

        if PurePosixPath(path).name == "tv_grab_file":

            candidates.append(uuid)

    require(
        len(candidates) == 1,
        "XMLTV_MODULE_NOT_UNIQUE",
    )

    return candidates[0]


def changes_for(node, desired):

    props = properties(node)

    changes = {}

    for key, value in desired.items():

        observed = property_value(
            props, key, type(value)
        )

        if observed == value:
            continue

        require(
            not props[key].get("rdonly")
            and not props[key].get("readonly"),
            "PROPERTY_READ_ONLY:" + key,
        )

        changes[key] = value

    return changes


def save(api_post, endpoint, payload):

    ok, code, _ = api_post(
        endpoint,
        {"node": json.dumps(payload)},
        timeout_s=15,
    )

    require(
        ok is True
        and 200 <= code < 300,
        "API_SAVE_FAILED:" + endpoint,
    )


def reconcile(
    api_post,
    load,
    save_endpoint,
    desired,
    uuid=None,
):

    before = load()

    changes = changes_for(
        before, desired
    )

    if not changes:
        return "UNCHANGED"

    payload = dict(changes)

    if uuid is not None:
        payload["uuid"] = uuid

    save(
        api_post,
        save_endpoint,
        payload,
    )

    require(
        not changes_for(load(), desired),
        "CONFIG_WRITE_NOT_CONFIRMED",
    )

    return "UPDATED"


def ensure_config(
    api_get=_tvh_api_get_json,
    api_post=_tvh_api_post_form,
    *,
    authorized=False,
):

    if authorized is not True:
        return {"status": "NOT_AUTHORIZED"}

    # Resolver primero el modulo correcto.
    # No escribir si su identidad es ambigua.

    uuid = find_xmltv_module(api_get)

    def general():
        return single_node(
            api_get, "config/load"
        )

    def epg():
        return single_node(
            api_get, "epggrab/config/load"
        )

    def xmltv():

        node = load_module(
            api_get, uuid
        )

        require(
            node.get("class") == XMLTV_CLASS
            and PurePosixPath(
                property_value(
                    properties(node), "path", str
                )
            ).name == "tv_grab_file",
            "XMLTV_MODULE_IDENTITY_CHANGED",
        )

        return node

    # Validar las tres configuraciones antes de escribir.

    general_desired = {
        "http_user_agent": USER_AGENT,
    }

    epg_desired = {
        "channel_rename": False,
    }

    xmltv_desired = {
        "enabled": True,
        "scrape_extra": True,
    }

    changes_for(general(), general_desired)
    changes_for(epg(), epg_desired)
    changes_for(xmltv(), xmltv_desired)

    result = {
        "general": reconcile(
            api_post,
            general,
            "config/save",
            general_desired,
        ),
        "epg": reconcile(
            api_post,
            epg,
            "epggrab/config/save",
            epg_desired,
        ),
        "xmltv": reconcile(
            api_post,
            xmltv,
            "idnode/save",
            xmltv_desired,
            uuid=uuid,
        ),
    }

    result["status"] = (
        "UPDATED"
        if "UPDATED" in result.values()
        else "UNCHANGED"
    )

    return result
