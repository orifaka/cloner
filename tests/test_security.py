from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "packages" / "core"),
    str(ROOT / "packages" / "deploy"),
]

from platform_core.config import Settings
from platform_core.security import TokenCipher, generate_slug
from platform_deploy.token_validator import TOKEN_RE


def test_token_cipher_roundtrip() -> None:
    settings = Settings(
        BUILDER_BOT_TOKEN="1:test",
        AES_SECRET_KEY="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        JWT_SECRET_KEY="jwt-secret-key-at-least-32-characters!",
    )
    cipher = TokenCipher(settings)
    plain = "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
    enc = cipher.encrypt(plain)
    assert enc != plain
    assert cipher.decrypt(enc) == plain


def test_slug_and_token_regex() -> None:
    assert len(generate_slug(12)) == 12
    assert TOKEN_RE.match("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw")
