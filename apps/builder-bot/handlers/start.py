from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from platform_billing.service import BillingService
from platform_core.config import Settings

from keyboards import main_menu
from texts import t_home, t_support
from ui import safe_delete_message, show

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    settings: Settings,
) -> None:
    await state.clear()
    user = message.from_user
    if not user:
        return
    await billing.ensure_user(
        telegram_id=user.id,
        username=user.username,
        full_name=user.full_name,
        language=user.language_code or settings.default_language,
    )
    await safe_delete_message(message)
    await show(
        message.bot,
        message.chat.id,
        state,
        t_home(settings),
        reply_markup=main_menu(),
        wipe=False,
    )


@router.message(Command("help", "panel", "commands"))
async def cmd_help(message: Message, state: FSMContext, settings: Settings) -> None:
    await safe_delete_message(message)
    await show(
        message.bot,
        message.chat.id,
        state,
        t_home(settings)
        + "\n\n<code>/start /open /status /restart /stop /logs /cancel</code>",
        reply_markup=main_menu(),
    )


@router.message(Command("support"))
async def cmd_support(message: Message, state: FSMContext, settings: Settings) -> None:
    await safe_delete_message(message)
    await show(message.bot, message.chat.id, state, t_support(settings.support_url), main_menu())
