# -*- coding: utf-8 -*-
"""ChaCha20-Poly1305 (RFC 8439) en Python puro; sin dependencias externas.

Formato MQC2: prefijo ASCII + base64(nonce[12] + ciphertext + tag[16]).
La confidencialidad depende de que la clave del dispositivo sea secreta.
"""
import base64
import hashlib
import hmac
import os
import struct

MAGIC = "MQC2:"
AAD = b"masQelec:crypto:v2"
_KEY_DOMAIN = b"masQelec:chacha20-poly1305:v2\x00"
_MASK32 = 0xffffffff
_P = (1 << 130) - 5


def _rotl32(v, n):
    return ((v << n) & _MASK32) | (v >> (32 - n))


def _quarter_round(s, a, b, c, d):
    s[a] = (s[a] + s[b]) & _MASK32
    s[d] = _rotl32(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & _MASK32
    s[b] = _rotl32(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & _MASK32
    s[d] = _rotl32(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & _MASK32
    s[b] = _rotl32(s[b] ^ s[c], 7)


def _block(key, counter, nonce):
    if len(key) != 32 or len(nonce) != 12 or not 0 <= counter <= _MASK32:
        raise ValueError("ChaCha20: key/nonce/counter inválido")
    initial = list(struct.unpack("<16I", b"expand 32-byte k" + key + struct.pack("<I", counter) + nonce))
    work = initial[:]
    for _ in range(10):
        _quarter_round(work, 0, 4, 8, 12)
        _quarter_round(work, 1, 5, 9, 13)
        _quarter_round(work, 2, 6, 10, 14)
        _quarter_round(work, 3, 7, 11, 15)
        _quarter_round(work, 0, 5, 10, 15)
        _quarter_round(work, 1, 6, 11, 12)
        _quarter_round(work, 2, 7, 8, 13)
        _quarter_round(work, 3, 4, 9, 14)
    return struct.pack("<16I", *((work[i] + initial[i]) & _MASK32 for i in range(16)))


def _xor_stream(data, key, nonce):
    if (len(data) + 63) // 64 >= (1 << 32):
        raise ValueError("ChaCha20: mensaje demasiado largo")
    result = bytearray(len(data))
    for offset in range(0, len(data), 64):
        block = _block(key, 1 + offset // 64, nonce)
        part = data[offset:offset + 64]
        result[offset:offset + len(part)] = bytes(x ^ y for x, y in zip(part, block))
    return bytes(result)


def _poly1305(msg, one_time_key):
    if len(one_time_key) != 32:
        raise ValueError("Poly1305: clave inválida")
    r = int.from_bytes(one_time_key[:16], "little") & 0x0ffffffc0ffffffc0ffffffc0fffffff
    s = int.from_bytes(one_time_key[16:], "little")
    acc = 0
    for i in range(0, len(msg), 16):
        chunk = msg[i:i + 16]
        acc = ((acc + int.from_bytes(chunk + b"\x01", "little")) * r) % _P
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _pad16(data):
    return b"\x00" * ((-len(data)) % 16)


def _tag(key, nonce, aad, ciphertext):
    auth_key = _block(key, 0, nonce)[:32]
    mac_input = (aad + _pad16(aad) + ciphertext + _pad16(ciphertext)
                 + struct.pack("<QQ", len(aad), len(ciphertext)))
    return _poly1305(mac_input, auth_key)


def _aead_encrypt(key, nonce, plaintext, aad=b""):
    ciphertext = _xor_stream(plaintext, key, nonce)
    return ciphertext, _tag(key, nonce, aad, ciphertext)


def _aead_decrypt(key, nonce, ciphertext, tag, aad=b""):
    if len(tag) != 16 or not hmac.compare_digest(_tag(key, nonce, aad, ciphertext), tag):
        raise ValueError("Autenticación fallida: contenido o clave incorrectos")
    return _xor_stream(ciphertext, key, nonce)


def _derive_key(device_key):
    if not isinstance(device_key, bytes) or len(device_key) != 32:
        raise ValueError("Se requiere clave de dispositivo de 32 bytes")
    return hashlib.sha256(_KEY_DOMAIN + device_key).digest()


def encrypt_v2(plaintext, device_key):
    """Devuelve texto MQC2 usando un nonce aleatorio de 96 bits."""
    if not isinstance(plaintext, bytes):
        raise TypeError("plaintext debe ser bytes")
    nonce = os.urandom(12)
    ciphertext, tag = _aead_encrypt(_derive_key(device_key), nonce, plaintext, AAD)
    return MAGIC + base64.b64encode(nonce + ciphertext + tag).decode("ascii")


def decrypt_v2(text, device_key):
    if isinstance(text, bytes):
        text = text.decode("ascii", "strict")
    if not isinstance(text, str) or not text.strip().startswith(MAGIC):
        raise ValueError("Formato MQC2 no encontrado")
    payload = base64.b64decode(text.strip()[len(MAGIC):], validate=True)
    if len(payload) < 28:
        raise ValueError("Payload MQC2 demasiado corto")
    nonce, ciphertext, tag = payload[:12], payload[12:-16], payload[-16:]
    return _aead_decrypt(_derive_key(device_key), nonce, ciphertext, tag, AAD)
