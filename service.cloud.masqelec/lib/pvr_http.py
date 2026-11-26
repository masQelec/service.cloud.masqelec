# -*- coding: utf-8 -*-
"""Cliente HTTP autenticado para Tvheadend local."""

import os
import json
import urllib.request
import urllib.error
import urllib.parse

TVH_HTTP_PORT = 9981

TVH_AUTH_FILE = (
    "/storage/.kodi/userdata/addon_data/"
    "service.cloud.masqelec/tvh_auth.json"
)

UA = "KodiELEC/1.0"

_TVH_DIGEST_OPENER = None
_TVH_DIGEST_USERPASS = None  # (user, pass)


def _tvh_read_http_auth() -> tuple[str, str]:
    """Lee credenciales de TVH desde TVH_AUTH_FILE.

    Soporta:
      - user+pass (Basic Auth)
      - user sin pass (TVH con auth "usuario sin contraseña")
    """
    try:
        if not os.path.exists(TVH_AUTH_FILE):
            return "", ""
        with open(TVH_AUTH_FILE, "r", encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return "", ""
        u = (data.get("username") or data.get("user") or "").strip()
        p = (data.get("password") or data.get("pass") or "")
        p = (p if isinstance(p, str) else "").strip()
        return (u, p) if u else ("", "")
    except Exception:
        return "", ""


_TVH_HTTP_AUTH_CACHE: tuple[str, str] | None = None
_TVH_BASIC_OPENER = None
_TVH_BASIC_USERPASS: tuple[str, str] | None = None


def _tvh_get_http_auth() -> tuple[str, str]:
    """Credenciales cacheadas (evita leer JSON en cada request)."""
    global _TVH_HTTP_AUTH_CACHE
    if _TVH_HTTP_AUTH_CACHE is None:
        _TVH_HTTP_AUTH_CACHE = _tvh_read_http_auth()
    return _TVH_HTTP_AUTH_CACHE


def _tvh_urlopen(req: urllib.request.Request, timeout_s: float):
    """Abre request a TVH.

    - Sin credenciales: directo.
    - user+pass: Basic Auth via opener.
    - user sin pass: NO fuerza Authorization; se usará `username=` inyectado en GET/POST.
    """
    u, p = _tvh_get_http_auth()
    if not u:
        return urllib.request.urlopen(req, timeout=float(timeout_s))

    if not p:
        # Importante: NO enviar Authorization: Basic user:
        return urllib.request.urlopen(req, timeout=float(timeout_s))

    global _TVH_BASIC_OPENER, _TVH_BASIC_USERPASS
    if _TVH_BASIC_OPENER is None or _TVH_BASIC_USERPASS != (u, p):
        pm = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        base = f"http://127.0.0.1:{int(TVH_HTTP_PORT)}/"
        pm.add_password(None, base, u, p)
        handler = urllib.request.HTTPBasicAuthHandler(pm)
        _TVH_BASIC_OPENER = urllib.request.build_opener(handler)
        _TVH_BASIC_USERPASS = (u, p)

    return _TVH_BASIC_OPENER.open(req, timeout=float(timeout_s))


def _tvh_api_get(api_path: str, query: dict | None = None, timeout_s: float = 10.0) -> tuple[bool, int, str]:
    host = "127.0.0.1"

    q = dict(query or {})
    # auth: user sin pass -> TVH suele aceptar ?username=USER
    u, p = _tvh_get_http_auth()
    if u and not p and "username" not in q:
        q["username"] = u

    qs = urllib.parse.urlencode(q)
    url = f"http://{host}:{int(TVH_HTTP_PORT)}/api/{api_path.lstrip('/')}{('?' + qs) if qs else ''}"

    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", UA)
    req.add_header("Accept", "*/*")
    req.add_header("Connection", "close")

    try:
        with _tvh_urlopen(req, timeout_s) as r:
            code = int(getattr(r, "status", 200) or 200)
            body = (r.read() or b"").decode("utf-8", "replace")
            return True, code, body
    except Exception as e:
        try:
            code = int(getattr(e, "code", 0) or 0)
            body = (e.read() or b"").decode("utf-8", "replace") if hasattr(e, "read") else str(e)
            return False, code, body
        except Exception:
            return False, 0, str(e)
        finally:
            if isinstance(e, urllib.error.HTTPError):
                try:
                    e.close()
                except Exception:
                    pass


def _tvh_api_get_json(api_path: str, query: dict | None = None, timeout_s: float = 10.0) -> tuple[bool, int, dict | None, str]:
    ok, code, body = _tvh_api_get(api_path, query=query, timeout_s=timeout_s)
    if not ok:
        return False, code, None, body or ""
    try:
        j = json.loads(body or "{}")
        return True, code, (j if isinstance(j, dict) else None), body or ""
    except Exception:
        return True, code, None, body or ""


def _tvh_api_post_form(api_path: str, form: dict, timeout_s: float = 15.0) -> tuple[bool, int, str]:
    host = "127.0.0.1"
    url = f"http://{host}:{int(TVH_HTTP_PORT)}/api/{api_path.lstrip('/')}"

    f = dict(form or {})
    # auth: user sin pass -> TVH suele aceptar username=USER también en POST form
    u, p = _tvh_get_http_auth()
    if u and not p and "username" not in f:
        f["username"] = u

    data = urllib.parse.urlencode(f).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("User-Agent", UA)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("Accept", "*/*")
    req.add_header("Connection", "close")

    try:
        with _tvh_urlopen(req, timeout_s) as r:
            code = int(getattr(r, "status", 200) or 200)
            body = (r.read() or b"").decode("utf-8", "replace")
            return True, code, body
    except Exception as e:
        try:
            code = int(getattr(e, "code", 0) or 0)
            body = (e.read() or b"").decode("utf-8", "replace") if hasattr(e, "read") else str(e)
            return False, code, body
        except Exception:
            return False, 0, str(e)
        finally:
            if isinstance(e, urllib.error.HTTPError):
                try:
                    e.close()
                except Exception:
                    pass
