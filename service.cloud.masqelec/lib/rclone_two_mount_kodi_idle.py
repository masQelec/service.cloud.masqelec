# -*- coding: utf-8 -*-
"""Validación segura de inactividad Kodi mediante JSON-RPC local.

Solo se acepta la respuesta explícita Player.GetActivePlayers == [].
Errores, valores desconocidos, timeouts o JSON ambiguo bloquean el corte.
No detiene reproducción ni importa xbmc: inyección para pruebas.
"""
import json

_REQUEST = json.dumps({
    "jsonrpc": "2.0", "id": 1, "method": "Player.GetActivePlayers",
}, separators=(",", ":"))


def is_playback_idle(rpc_call):
    """El callback debe ser xbmc.executeJSONRPC desde DENTRO de Kodi."""
    if not callable(rpc_call):
        return False
    try:
        raw = rpc_call(_REQUEST)
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "strict")
        if not isinstance(raw, str) or len(raw) > 65536:
            return False
        answer = json.loads(raw)
        if (not isinstance(answer, dict)
                or answer.get("jsonrpc") != "2.0"
                or type(answer.get("id")) is not int
                or answer["id"] != 1
                or "error" in answer
                or set(answer) != {"id", "jsonrpc", "result"}
                or not isinstance(answer["result"], list)):
            return False
        return answer["result"] == []
    except (Exception):
        return False
