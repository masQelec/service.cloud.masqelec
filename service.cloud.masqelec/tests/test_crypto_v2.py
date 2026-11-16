# -*- coding: utf-8 -*-
"""Tests RFC 8439 de criptografía pura, ejecutables sin Kodi ni dependencias."""
import base64
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib import chacha_pure as cc


class CryptoV2Tests(unittest.TestCase):
    def test_block_rfc8439(self):
        expected = bytes.fromhex(
            "10f1e7e4d13b5915500fdd1fa32071c4"
            "c7d1f4c733c068030422aa9ac3d46c4e"
            "d2826446079faa0914c2d705d98b02a2"
            "b5129cd1de164eb9cbd083e8a2503c4e")
        self.assertEqual(
            cc._block(bytes(range(32)), 1, bytes.fromhex("000000090000004a00000000")),
            expected,
        )

    def test_poly1305_rfc8439(self):
        key = bytes.fromhex(
            "85d6be7857556d337f4452fe42d506a8"
            "0103808afb0db2fd4abff6af4149f51b")
        tag = cc._poly1305(b"Cryptographic Forum Research Group", key)
        self.assertEqual(tag.hex(), "a8061dc1305136c6c22b8baf0c0127a9")

    def test_aead_rfc8439(self):
        key = bytes(range(0x80, 0xa0))
        nonce = bytes.fromhex("070000004041424344454647")
        aad = bytes.fromhex("50515253c0c1c2c3c4c5c6c7")
        plaintext = (
            b"Ladies and Gentlemen of the class of '99: If I could offer you "
            b"only one tip for the future, sunscreen would be it."
        )
        ciphertext, tag = cc._aead_encrypt(key, nonce, plaintext, aad)
        self.assertEqual(ciphertext[:16].hex(), "d31a8d34648e60db7b86afbc53ef7ec2")
        self.assertEqual(tag.hex(), "1ae10b594f09e26a7e902ecbd0600691")
        self.assertEqual(cc._aead_decrypt(key, nonce, ciphertext, tag, aad), plaintext)

    def test_roundtrip_and_tamper(self):
        key = hashlib.sha256(b"test-device-key").digest()
        for size in (0, 1, 15, 16, 17, 64, 129):
            plain = b"x" * size
            text = cc.encrypt_v2(plain, key)
            self.assertEqual(cc.decrypt_v2(text, key), plain)
            ciphertext = bytearray(base64.b64decode(text[len(cc.MAGIC):]))
            ciphertext[-1] ^= 1
            with self.assertRaises(ValueError):
                cc.decrypt_v2(cc.MAGIC + base64.b64encode(ciphertext).decode(), key)
            with self.assertRaises(ValueError):
                cc.decrypt_v2(text, b"\x00" * 32)


if __name__ == "__main__":
    unittest.main()
