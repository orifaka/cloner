from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx

TOKEN_RE = re.compile(r"^\d{6,15}:[A-Za-z0-9_-]{20,}$")


@dataclass(frozen=True)
class BotIdentity:
    id: int
    username: Optional[str]
    first_name: str
    can_join_groups: bool
    can_read_all_group_messages: bool
    supports_inline_queries: bool


class TokenValidationError(Exception):
    pass


async def validate_bot_token(token: str) -> BotIdentity:
    token = token.strip()
    if not TOKEN_RE.match(token):
        raise TokenValidationError(
            "Token formati noto'g'ri. BotFather dan olingan token shunday bo'ladi:\n"
            "<code>123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw</code>"
        )
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            data = resp.json()
    except httpx.HTTPError as exc:
        raise TokenValidationError(f"Telegram API ga ulanib bo'lmadi: {exc}") from exc

    if not data.get("ok"):
        desc = data.get("description") or "Unknown error"
        raise TokenValidationError(f"Token yaroqsiz: {desc}")

    result = data["result"]
    if not result.get("is_bot"):
        raise TokenValidationError("Bu token botga tegishli emas.")

    return BotIdentity(
        id=int(result["id"]),
        username=result.get("username"),
        first_name=result.get("first_name") or "Bot",
        can_join_groups=bool(result.get("can_join_groups", True)),
        can_read_all_group_messages=bool(result.get("can_read_all_group_messages", False)),
        supports_inline_queries=bool(result.get("supports_inline_queries", False)),
    )
