from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger("ops")


class OpsLogMiddleware(BaseMiddleware):
    """Log every user action to bot.log."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            if isinstance(event, Message):
                user = event.from_user
                text = (event.text or event.caption or "")[:200]
                uid = user.id if user else "?"
                uname = f"@{user.username}" if user and user.username else "-"
                logger.info("MSG  user=%s %s chat=%s text=%r", uid, uname, event.chat.id, text)
            elif isinstance(event, CallbackQuery):
                user = event.from_user
                uid = user.id if user else "?"
                uname = f"@{user.username}" if user and user.username else "-"
                logger.info("CB   user=%s %s data=%r", uid, uname, event.data)
        except Exception:  # noqa: BLE001
            logger.exception("ops log failed")

        try:
            return await handler(event, data)
        except Exception:
            logger.exception("handler failed")
            raise
