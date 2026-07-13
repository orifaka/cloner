from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from platform_core.config import Settings


def _aes_key_bytes(secret: str) -> bytes:
    """Derive a stable 32-byte AES key from configured secret."""
    raw = secret.encode("utf-8")
    if len(secret) == 64:
        try:
            return bytes.fromhex(secret)
        except ValueError:
            pass
    return hashlib.sha256(raw).digest()


class TokenCipher:
    """AES-256-GCM encryption for BotFather tokens at rest."""

    def __init__(self, settings: Settings) -> None:
        self._aesgcm = AESGCM(_aes_key_bytes(settings.aes_secret_key))

    def encrypt(self, plaintext: str) -> str:
        nonce = secrets.token_bytes(12)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt(self, payload: str) -> str:
        raw = base64.urlsafe_b64decode(payload.encode("ascii"))
        nonce, ciphertext = raw[:12], raw[12:]
        return self._aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")


class JWTService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create_access_token(self, subject: str, extra: Optional[dict[str, Any]] = None) -> str:
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._settings.jwt_expire_minutes)).timestamp()),
        }
        if extra:
            payload.update(extra)
        return jwt.encode(payload, self._settings.jwt_secret_key, algorithm=self._settings.jwt_algorithm)

    def decode_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._settings.jwt_secret_key,
            algorithms=[self._settings.jwt_algorithm],
        )


def generate_slug(length: int = 10) -> str:
    return secrets.token_hex(length // 2 + 1)[:length]


def generate_secret(length: int = 32) -> str:
    return secrets.token_urlsafe(length)


def generate_db_password(length: int = 24) -> str:
    return secrets.token_urlsafe(length)
