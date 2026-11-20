"""G3-N adapter for already-existing authenticated TVH helpers.

GET must be _tvh_api_get_json; POST must be _tvh_api_post_form.
No credentials or secrets are logged. Not connected to active addon yet.
"""
import json


class TvheadendAPIBlocked(ValueError):
    pass


_LIMITS = {"channeltag/grid": 200, "channel/grid": 20000}
_WRITES = {"channeltag/create", "idnode/delete"}


def make_snapshot_reader(get_json):
    def read():
        result = []
        for endpoint, limit in _LIMITS.items():
            ok, status, payload, _ = get_json(
                endpoint, query={"start": 0, "limit": limit, "all": 1}
            )
            if not ok or status != 200 or not isinstance(payload, dict):
                raise TvheadendAPIBlocked("TVH_READ_FAILED")
            entries = payload.get("entries")
            if (not isinstance(entries, list)
                    or type(payload.get("total")) is not int
                    or payload["total"] != len(entries)
                    or len(entries) > limit):
                raise TvheadendAPIBlocked("TVH_PARTIAL_GRID")
            result.append(payload)
        return tuple(result)
    return read


def make_writer(post_form):
    def post(endpoint, values):
        if endpoint not in _WRITES:
            raise TvheadendAPIBlocked("TVH_WRITE_ENDPOINT_NOT_ALLOWED")
        if not isinstance(values, dict):
            raise TvheadendAPIBlocked("INVALID_WRITE_PARAMS")
        if endpoint == "channeltag/create":
            if set(values) != {"conf"}:
                raise TvheadendAPIBlocked("INVALID_CREATE_PARAMS")
            try:
                conf = json.loads(values["conf"])
            except (TypeError, ValueError) as exc:
                raise TvheadendAPIBlocked("INVALID_CREATE_JSON") from exc
            if (not isinstance(conf, dict) or
                    not isinstance(conf.get("name"), str) or
                    not conf["name"].strip() or
                    conf.get("internal") is not False):
                raise TvheadendAPIBlocked("INVALID_CREATE_CONF")
        else:
            if set(values) != {"uuid"} or not isinstance(values["uuid"], str):
                raise TvheadendAPIBlocked("INVALID_DELETE_PARAMS")
        ok, status, response = post_form(endpoint, values)
        if not ok or status != 200:
            raise TvheadendAPIBlocked("TVH_WRITE_FAILED")
        if response:
            try:
                parsed = json.loads(response)
            except (TypeError, ValueError):
                # TVH versions may return plain text on successful mutation.
                return True
            if isinstance(parsed, dict) and (
                parsed.get("error") or parsed.get("success") is False
            ):
                raise TvheadendAPIBlocked("TVH_WRITE_REJECTED")
        return True
    return post
