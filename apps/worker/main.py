from __future__ import annotations

"""
Standalone worker for subscription lifecycle + health heartbeats.
Usually not required — builder-bot already runs the scheduler.
Use this process when you scale builder bot separately from jobs.
"""

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "packages" / "billing"))
sys.path.insert(0, str(ROOT / "packages" / "deploy"))
sys.path.insert(0, str(ROOT / "packages" / "monitoring"))

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from platform_billing.service import BillingService
from platform_core.config import get_settings
from platform_core.database import close_db, get_session_factory, init_db
from platform_deploy.engine import DeploymentEngine


async def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    await init_db(settings)
    factory = get_session_factory(settings)
    billing = BillingService(settings, factory)
    deploy = DeploymentEngine(settings, factory)
    bot = Bot(settings.builder_bot_token)

    scheduler = AsyncIOScheduler()

    async def tick() -> None:
        await billing.process_lifecycle(bot, deploy)

    scheduler.add_job(tick, "interval", minutes=15, id="lifecycle")
    scheduler.start()
    logging.info("Worker started")
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        scheduler.shutdown(wait=False)
        await close_db()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
