from __future__ import annotations

from typing import Optional

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
    for mid in data.get("ui_ids") or []:
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
    if wipe:
        await wipe_ui(bot, chat_id, state)
    msg = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    data = await state.get_data()
    ids = list(data.get("ui_ids") or [])
    ids.append(msg.message_id)
    await state.update_data(ui_ids=ids[-4:])
    return msg


async def replace_message(message: Message, text: str, reply_markup=None) -> Message:
    try:
        return await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest:
        try:
            await message.delete()
        except (TelegramBadRequest, TelegramForbiddenError):
            pass
        return await message.bot.send_message(message.chat.id, text, reply_markup=reply_markup)


async def safe_cb(callback, text: str | None = None, show_alert: bool = False) -> None:
    try:
        await callback.answer(text, show_alert=show_alert)
    except (TelegramBadRequest, TelegramForbiddenError):
        pass
