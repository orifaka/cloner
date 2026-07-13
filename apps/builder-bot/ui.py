from __future__ import annotations

"""Clean single-screen UI: old bot messages are deleted, not stacked."""

from typing import Any, Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.fsm.context import FSMContext
from aiogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup


async def safe_delete(bot: Bot, chat_id: int, message_id: int) -> None:
    try:
        await bot.delete_message(chat_id, message_id)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


async def safe_delete_message(message: Optional[Message]) -> None:
    if not message:
        return
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        pass


async def wipe_ui(bot: Bot, chat_id: int, state: FSMContext) -> None:
    data = await state.get_data()
    ids: Sequence[int] = data.get("ui_ids") or []
    for mid in ids:
        await safe_delete(bot, chat_id, int(mid))
    await state.update_data(ui_ids=[])


async def show(
    bot: Bot,
    chat_id: int,
    state: FSMContext,
    text: str,
    reply_markup: InlineKeyboardMarkup | ReplyKeyboardMarkup | None = None,
    *,
    wipe: bool = True,
) -> Message:
    """Send a fresh screen; optionally delete previous bot UI messages."""
    if wipe:
        await wipe_ui(bot, chat_id, state)
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    data = await state.get_data()
    ids = list(data.get("ui_ids") or [])
    ids.append(msg.message_id)
    # keep only last 3 bot screens max
    ids = ids[-3:]
    await state.update_data(ui_ids=ids)
    return msg


async def replace_message(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> Message:
    """Edit in place; if edit fails, delete and resend."""
    try:
        return await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        chat_id = message.chat.id
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return await message.bot.send_message(chat_id, text, reply_markup=reply_markup)


async def safe_callback_answer(callback: Any, text: str | None = None, show_alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
