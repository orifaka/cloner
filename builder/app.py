from __future__ import annotations

import logging
from pathlib import Path

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, ErrorEvent, Message, TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from builder.billing import BillingService
from builder.config import ROOT_DIR, Settings, get_settings
from builder.db import close_db, get_session_factory, init_db
from builder.deploy import DeploymentEngine
from builder.handlers import router
from builder import models  # noqa: F401 — register tables

logger = logging.getLogger("builder")


class OpsLogMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: TelegramObject, data: dict):
        try:
            if isinstance(event, Message) and event.from_user:
                t = (event.text or "")[:160]
                logger.info("MSG user=%s @%s %r", event.from_user.id, event.from_user.username, t)
            elif isinstance(event, CallbackQuery) and event.from_user:
                logger.info("CB  user=%s %r", event.from_user.id, event.data)
        except Exception:  # noqa: BLE001
            pass
        return await handler(event, data)


async def _on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    if isinstance(exc, TelegramBadRequest):
        m = str(exc).lower()
        if any(x in m for x in ("query is too old", "message is not modified", "message to edit not found", "message to delete not found")):
            logger.warning("soft: %s", exc)
            return True
    if isinstance(exc, (TelegramForbiddenError, TelegramRetryAfter)):
        logger.warning("soft: %s", exc)
        return True
    # Never leak stack traces to users — only log server-side
    logger.exception("error: %s", exc)
    try:
        upd = event.update
        chat_id = None
        if upd.message and upd.message.chat:
            chat_id = upd.message.chat.id
        elif upd.callback_query and upd.callback_query.message:
            chat_id = upd.callback_query.message.chat.id
        if chat_id and event.bot:
            from builder.copy import friendly_error
            from builder.keyboards import after_error_kb

            await event.bot.send_message(chat_id, friendly_error(exc), reply_markup=after_error_kb())
    except Exception:  # noqa: BLE001
        pass
    return True


async def run_bot() -> None:
    settings = get_settings()
    logger.info("=== start === payments=%s template=%s", settings.payments_enabled, settings.template_dir)

    await init_db(settings)
    sf = get_session_factory(settings)
    billing = BillingService(settings, sf)
    deploy = DeploymentEngine(settings, sf)

    bot = Bot(settings.builder_bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    me = await bot.get_me()
    if me.username:
        settings.builder_bot_username = me.username
    logger.info("online @%s id=%s", me.username, me.id)

    dp = Dispatcher(storage=MemoryStorage())
    dp.errors.register(_on_error)
    dp.update.middleware(OpsLogMiddleware())
    dp.include_router(router)

    scheduler = AsyncIOScheduler()

    async def life() -> None:
        try:
            await billing.process_lifecycle(bot, deploy)
        except Exception:  # noqa: BLE001
            logger.exception("lifecycle")

    async def daily_backups() -> None:
        """Auto-backup all running tenant bots once a day."""
        try:
            from sqlalchemy import select
            from builder.models import Deployment

            sf2 = get_session_factory()
            async with sf2() as s:
                deps = (
                    await s.execute(select(Deployment).where(Deployment.status == "running"))
                ).scalars().all()
            for d in deps:
                try:
                    await deploy.backup(d.id)
                    logger.info("auto-backup dep=%s", d.id)
                except Exception:  # noqa: BLE001
                    logger.warning("backup fail dep=%s", d.id)
        except Exception:  # noqa: BLE001
            logger.exception("daily_backups")

    async def health_watch() -> None:
        """Restart dead running processes (watchdog)."""
        try:
            from sqlalchemy import select
            from builder.models import Deployment

            sf2 = get_session_factory()
            async with sf2() as s:
                deps = (
                    await s.execute(select(Deployment).where(Deployment.status == "running"))
                ).scalars().all()
            for d in deps:
                if d.process_pid and not deploy._pid_alive(d.process_pid):
                    logger.warning("dead process dep=%s pid=%s — restart", d.id, d.process_pid)
                    try:
                        await deploy.start(d.id)
                    except Exception:  # noqa: BLE001
                        logger.exception("watchdog restart fail dep=%s", d.id)
        except Exception:  # noqa: BLE001
            logger.exception("health_watch")

    scheduler.add_job(life, "interval", minutes=30, id="life", replace_existing=True)
    scheduler.add_job(daily_backups, "cron", hour=3, minute=15, id="backups", replace_existing=True)
    scheduler.add_job(health_watch, "interval", minutes=5, id="health", replace_existing=True)
    scheduler.start()

    try:
        logger.info("polling…  log → %s", ROOT_DIR / "bot.log")
        await dp.start_polling(
            bot,
            settings=settings,
            billing=billing,
            deploy=deploy,
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
        )
    finally:
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()
        logger.info("=== stop ===")
