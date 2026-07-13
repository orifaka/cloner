from __future__ import annotations

"""
Token → auto deploy (background).

CRITICAL: never await long deploy inside the update handler.
FSM lock would freeze the user until pip/copy finish.
"""

import asyncio
import logging
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from platform_billing.service import BillingService
from platform_core.config import Settings
from platform_core.enums import SubscriptionStatus
from platform_deploy.engine import DeploymentEngine
from platform_deploy.token_validator import TokenValidationError

from keyboards import main_menu, status_kb
from texts import (
    t_ask_token,
    t_busy,
    t_cancelled,
    t_checking,
    t_deploying,
    t_failed,
    t_invalid,
    t_need_sub,
    t_progress,
    t_ready,
)
from ui import replace_message, safe_delete_message, show

logger = logging.getLogger(__name__)
router = Router(name="deploy")

TOKEN_RE = re.compile(r"^\d{6,15}:[A-Za-z0-9_-]{20,}$")


class DeployStates(StatesGroup):
    waiting_token = State()


# In-memory guard: one deploy per telegram user
_active_deploys: set[int] = set()


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    await safe_delete_message(message)
    await state.set_state(None)
    await state.update_data(bot_token=None, deploying=False)
    await show(message.bot, message.chat.id, state, t_cancelled(), main_menu())


@router.message(Command("token"))
async def cmd_token(message: Message, state: FSMContext, billing: BillingService, settings: Settings) -> None:
    user = message.from_user
    if not user:
        return
    await safe_delete_message(message)
    panel = await billing.get_user_panel(user.id)
    sub = panel.get("subscription")
    if not sub or sub.status not in {
        SubscriptionStatus.ACTIVE.value,
        SubscriptionStatus.GRACE.value,
    }:
        if settings.payments_enabled:
            await show(message.bot, message.chat.id, state, t_need_sub(), main_menu())
            return
        result = await billing.grant_test_subscription(user.id)
        sub = result["subscription"]
    await state.set_state(DeployStates.waiting_token)
    await state.update_data(subscription_id=sub.id, deploying=False)
    await show(message.bot, message.chat.id, state, t_ask_token(), main_menu())


@router.message(StateFilter(DeployStates.waiting_token), F.text)
async def on_token(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
) -> None:
    """Receive token, validate, start background deploy. Handler returns immediately after launch."""
    user = message.from_user
    if not user:
        return

    raw = (message.text or "").strip()
    # Always remove token message from chat
    await safe_delete_message(message)

    if raw.startswith("/"):
        return

    if not TOKEN_RE.match(raw):
        await show(
            message.bot,
            message.chat.id,
            state,
            t_invalid("Format: <code>123456:AA...</code>"),
            main_menu(),
        )
        # stay in waiting_token
        await state.set_state(DeployStates.waiting_token)
        return

    data = await state.get_data()
    if data.get("deploying") or user.id in _active_deploys:
        await show(message.bot, message.chat.id, state, t_busy(), main_menu())
        return

    panel = await billing.get_user_panel(user.id)
    sub = panel.get("subscription")
    db_user = panel.get("user")
    if not db_user:
        await billing.ensure_user(user.id, user.username, user.full_name)
        panel = await billing.get_user_panel(user.id)
        db_user = panel.get("user")
        sub = panel.get("subscription")

    if not sub or sub.status not in {
        SubscriptionStatus.ACTIVE.value,
        SubscriptionStatus.GRACE.value,
    }:
        if not settings.payments_enabled:
            result = await billing.grant_test_subscription(user.id)
            sub = result["subscription"]
            db_user = result["user"]
        else:
            await show(message.bot, message.chat.id, state, t_need_sub(), main_menu())
            await state.clear()
            return

    check_msg = await show(message.bot, message.chat.id, state, t_checking(), main_menu())
    logger.info("TOKEN received user=%s — validating…", user.id)

    try:
        identity = await asyncio.wait_for(deploy.validate_token(raw), timeout=20.0)
        logger.info("TOKEN ok user=%s bot=@%s id=%s", user.id, identity.username, identity.id)
    except TokenValidationError as exc:
        logger.warning("TOKEN invalid user=%s err=%s", user.id, exc)
        await replace_message(check_msg, t_invalid(str(exc)))
        await state.set_state(DeployStates.waiting_token)
        return
    except asyncio.TimeoutError:
        logger.warning("TOKEN timeout user=%s", user.id)
        await replace_message(check_msg, t_invalid("Telegram API timeout. Qayta yuboring."))
        await state.set_state(DeployStates.waiting_token)
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("token validate failed user=%s", user.id)
        await replace_message(check_msg, t_invalid(str(exc)[:200]))
        await state.set_state(DeployStates.waiting_token)
        return

    # Leave token state so user is not locked; mark deploying
    await state.set_state(None)
    await state.update_data(
        deploying=True,
        bot_token=None,  # do not keep plain token in FSM
        subscription_id=sub.id,
    )
    await replace_message(check_msg, t_deploying(identity.username))

    _active_deploys.add(user.id)
    logger.info("DEPLOY background start user=%s target=@%s", user.id, identity.username)
    asyncio.create_task(
        _run_deploy_job(
            bot=message.bot,
            chat_id=message.chat.id,
            progress_message_id=check_msg.message_id,
            telegram_user_id=user.id,
            db_user_id=db_user.id,
            subscription_id=sub.id,
            bot_token=raw,
            identity=identity,
            deploy=deploy,
            settings=settings,
            state=state,
        ),
        name=f"deploy-{user.id}",
    )


@router.message(F.text.regexp(TOKEN_RE))
async def on_token_any_state(
    message: Message,
    state: FSMContext,
    billing: BillingService,
    deploy: DeploymentEngine,
    settings: Settings,
) -> None:
    """Accept token even if user skipped /open (auto grant in test mode)."""
    # If already in waiting_token, the other handler runs — skip duplicate
    current = await state.get_state()
    if current == DeployStates.waiting_token.state:
        return
    await state.set_state(DeployStates.waiting_token)
    await on_token(message, state, billing, deploy, settings)


async def _run_deploy_job(
    *,
    bot: Bot,
    chat_id: int,
    progress_message_id: int,
    telegram_user_id: int,
    db_user_id: int,
    subscription_id: int,
    bot_token: str,
    identity,
    deploy: DeploymentEngine,
    settings: Settings,
    state: FSMContext,
) -> None:
    """Background worker — does not hold FSM update lock."""

    async def edit(text: str) -> None:
        try:
            await bot.edit_message_text(text, chat_id=chat_id, message_id=progress_message_id)
        except Exception:  # noqa: BLE001
            try:
                await bot.send_message(chat_id, text, reply_markup=main_menu())
            except Exception:  # noqa: BLE001
                pass

    async def progress(step: str) -> None:
        logger.info("DEPLOY progress user=%s @%s | %s", telegram_user_id, identity.username, step)
        await edit(t_progress(identity.username, step))

    try:
        await progress("📁 Nusxa olinmoqda…")
        dep_id = await deploy.deploy_for_user(
            user_id=db_user_id,
            subscription_id=subscription_id,
            bot_token=bot_token,
            bot_identity=identity,
            progress_callback=progress,
        )
        await edit(t_ready(identity.username, settings.subscription_days))
        try:
            await bot.send_message(
                chat_id,
                f"#{dep_id} · boshqaruv:",
                reply_markup=status_kb(),
            )
        except Exception:  # noqa: BLE001
            pass
        logger.info("DEPLOY OK user=%s dep=%s bot=@%s", telegram_user_id, dep_id, identity.username)
    except Exception as exc:  # noqa: BLE001
        logger.exception("DEPLOY FAIL user=%s err=%s", telegram_user_id, exc)
        await edit(t_failed(str(exc)))
    finally:
        _active_deploys.discard(telegram_user_id)
        try:
            await state.update_data(deploying=False)
        except Exception:  # noqa: BLE001
            pass
        logger.info("DEPLOY finished user=%s", telegram_user_id)
