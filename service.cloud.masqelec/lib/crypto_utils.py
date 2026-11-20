# -*- coding: utf-8 -*-
"""Descifrado MQC2 estricto. No admite los formatos Feistel heredados."""

from lib import log_utils
from lib.chacha_pure import decrypt_v2, encrypt_v2


def decrypt(encrypted_text, key):
    """Devuelve bytes autenticados, o None si el formato/clave son inválidos."""
    try:
        return decrypt_v2(encrypted_text, key)
    except Exception as exc:
        # Nunca registrar tokens, claves ni texto descifrado.
        log_utils.write_log(
            "MQC2: descifrado/autenticación fallida ({})".format(type(exc).__name__),
            "ERROR",
        )
        return None
