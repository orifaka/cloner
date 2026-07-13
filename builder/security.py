from __future__ import annotations

import base64
import hashlib
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from builder.config import Settings


def _key(secret: str) -> bytes:
    if len(secret) == 64:
        try:
            return bytes.fromhex(secret)
        except ValueError:
            pass
    return hashlib.sha256(secret.encode()).digest()


class TokenCipher:
    def __init__(self, settings: Settings) -> None:
        self._aes = AESGCM(_key(settings.aes_secret_key))

    def encrypt(self, plain: str) -> str:
        nonce = secrets.token_bytes(12)
        ct = self._aes.encrypt(nonce, plain.encode(), None)
        return base64.urlsafe_b64encode(nonce + ct).decode("ascii")

    def decrypt(self, payload: str) -> str:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        return self._aes.decrypt(raw[:12], raw[12:], None).decode()


def generate_slug(n: int = 12) -> str:
    return secrets.token_hex((n + 1) // 2)[:n]
