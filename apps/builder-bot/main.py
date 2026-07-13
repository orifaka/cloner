from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

# Make packages and this app importable when running: python apps/builder-bot/main.py
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "packages" / "billing"))
sys.path.insert(0, str(ROOT / "packages" / "deploy"))
sys.path.insert(0, str(ROOT / "packages" / "monitoring"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from platform_billing.service import BillingService
from platform_core.config import get_settings
from platform_core.database import close_db, get_session_factory, init_db
from platform_deploy.engine import DeploymentEngine
from platform_monitoring.service import MonitoringService

from handlers import deploy, payment, panel, start
from logging_setup import setup_logging
from middleware_log import OpsLogMiddleware

logger = logging.getLogger("builder")


async def global_error_handler(event: ErrorEvent) -> bool:
    exc = event.exception
    if isinstance(exc, TelegramBadRequest):
        msg = str(exc).lower()
        if any(
            s in msg
            for s in (
                "query is too old",
                "query id is invalid",
                "message is not modified",
                "message to edit not found",
                "message to delete not found",
            )
        ):
            logger.warning("Telegram soft: %s", exc)
            return True
    if isinstance(exc, (TelegramForbiddenError, TelegramRetryAfter)):
        logger.warning("Telegram soft: %s", exc)
        return True
    logger.exception("Unhandled update error: %s", exc)
    return True


async def main() -> None:
    settings = get_settings()
    log_path = setup_logging(ROOT, settings.log_level)
    logger.info("=== Builder start === log_file=%s", log_path)
    logger.info("payments_enabled=%s deploy_provider=%s", settings.payments_enabled, settings.deploy_provider)
    logger.info("template=%s", settings.template_dir)

    await init_db(settings)
    logger.info("DB ready: %s", settings.platform_database_url)
    session_factory = get_session_factory(settings)

    billing = BillingService(settings, session_factory)
    deploy_engine = DeploymentEngine(settings, session_factory)
    monitor = MonitoringService()

    bot = Bot(
        settings.builder_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    me = await bot.get_me()
    if me.username:
        settings.builder_bot_username = me.username
    logger.info("Bot online: @%s id=%s", me.username, me.id)

    dp = Dispatcher(storage=MemoryStorage())
    dp["settings"] = settings
    dp["billing"] = billing
    dp["deploy"] = deploy_engine
    dp["monitor"] = monitor

    dp.workflow_data.update(
        settings=settings,
        billing=billing,
        deploy=deploy_engine,
        monitor=monitor,
    )
    dp.errors.register(global_error_handler)
    dp.update.middleware(OpsLogMiddleware())

    dp.include_router(start.router)
    dp.include_router(payment.router)
    dp.include_router(deploy.router)
    dp.include_router(panel.router)

    scheduler = AsyncIOScheduler()

    async def lifecycle_job() -> None:
        try:
            logger.info("lifecycle tick")
            await billing.process_lifecycle(bot, deploy_engine)
        except Exception:  # noqa: BLE001
            logger.exception("lifecycle job failed")

    scheduler.add_job(lifecycle_job, "interval", minutes=30, id="subscription_lifecycle", replace_existing=True)
    scheduler.start()
    logger.info("Scheduler started")

    try:
        logger.info("Polling start…")
        await dp.start_polling(
            bot,
            settings=settings,
            billing=billing,
            deploy=deploy_engine,
            monitor=monitor,
            allowed_updates=["message", "callback_query", "pre_checkout_query", "successful_payment"],
            drop_pending_updates=True,
        )
    finally:
        logger.info("Shutting down…")
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()
        logger.info("=== Builder stopped ===")


if __name__ == "__main__":
    if sys.platform != "win32":
        try:
            import uvloop

            uvloop.install()
        except ImportError:
            pass
    asyncio.run(main())
