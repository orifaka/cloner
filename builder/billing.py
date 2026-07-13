from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import LabeledPrice
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from builder.config import Settings
from builder.models import Deployment, Payment, Subscription, User

logger = logging.getLogger("builder.billing")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class BillingService:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.sf = session_factory

    async def ensure_user(
        self,
        telegram_id: int,
        username: Optional[str],
        full_name: str,
        language: str = "uz",
    ) -> User:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if u:
                u.username = username
                u.full_name = full_name or u.full_name
                if telegram_id in self.settings.admin_telegram_ids:
                    u.role = "admin"
                await s.commit()
                await s.refresh(u)
                return u
            u = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                language=language,
                role="admin" if telegram_id in self.settings.admin_telegram_ids else "user",
            )
            s.add(u)
            await s.commit()
            await s.refresh(u)
            return u

    async def get_panel(self, telegram_id: int) -> dict[str, Any]:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                return {"user": None}
            sub = (
                await s.execute(
                    select(Subscription)
                    .options(selectinload(Subscription.deployment))
                    .where(Subscription.user_id == u.id, Subscription.status.in_(["active", "grace", "pending"]))
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            dep = (
                await s.execute(
                    select(Deployment)
                    .where(Deployment.user_id == u.id, Deployment.status != "deleted")
                    .order_by(Deployment.id.desc())
                )
            ).scalars().first()
            days = None
            exp = as_utc(sub.expires_at) if sub else None
            if exp:
                days = max(0, int((exp - utcnow()).total_seconds() // 86400))
            return {"user": u, "subscription": sub, "deployment": dep, "days_left": days}

    async def grant_test_subscription(self, telegram_id: int) -> dict[str, Any]:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                raise ValueError("User topilmadi")
            sub = (
                await s.execute(
                    select(Subscription)
                    .where(Subscription.user_id == u.id)
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            now = utcnow()
            if not sub or sub.status in {"expired", "cancelled"}:
                sub = Subscription(user_id=u.id, price_stars=0)
                s.add(sub)
            sub.status = "active"
            sub.starts_at = sub.starts_at or now
            sub.expires_at = now + timedelta(days=self.settings.subscription_days)
            sub.grace_until = sub.expires_at + timedelta(hours=self.settings.grace_period_hours)
            sub.price_stars = 0
            sub.reminder_7d_sent = sub.reminder_3d_sent = sub.reminder_24h_sent = False
            await s.commit()
            await s.refresh(sub)
            logger.info("test sub granted user=%s exp=%s", telegram_id, sub.expires_at)
            return {"user": u, "subscription": sub}

    async def create_invoice_payload(self, telegram_id: int, purpose: str = "new_subscription") -> str:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                raise ValueError("User topilmadi")
            sub = (
                await s.execute(
                    select(Subscription)
                    .where(Subscription.user_id == u.id, Subscription.status.in_(["active", "grace", "pending"]))
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            if not sub or sub.status in {"expired", "cancelled"}:
                sub = Subscription(user_id=u.id, price_stars=self.settings.subscription_price_stars)
                s.add(sub)
                await s.flush()
            payload = f"sub:{sub.id}:u:{u.id}:p:{purpose}:{int(utcnow().timestamp())}"
            s.add(
                Payment(
                    user_id=u.id,
                    subscription_id=sub.id,
                    amount_stars=self.settings.subscription_price_stars,
                    purpose=purpose,
                    payload=payload,
                    status="pending",
                )
            )
            await s.commit()
            return payload

    async def send_stars_invoice(self, bot: Bot, chat_id: int, payload: str) -> None:
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"{self.settings.brand_name} obuna",
            description=f"Mafia bot hosting — {self.settings.subscription_days} kun",
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(label="30 kun", amount=self.settings.subscription_price_stars)],
        )

    async def activate_from_payment(
        self,
        payload: str,
        charge_id: Optional[str],
        provider_id: Optional[str],
    ) -> dict[str, Any]:
        async with self.sf() as s:
            pay = (await s.execute(select(Payment).where(Payment.payload == payload))).scalar_one_or_none()
            if not pay:
                raise ValueError("Payment topilmadi")
            if pay.status == "success":
                sub = await s.get(Subscription, pay.subscription_id)
                return {"payment": pay, "subscription": sub, "already": True}
            pay.status = "success"
            pay.telegram_payment_charge_id = charge_id
            pay.provider_payment_charge_id = provider_id
            pay.paid_at = utcnow()
            sub = await s.get(Subscription, pay.subscription_id)
            if not sub:
                raise ValueError("Subscription yo'q")
            now = utcnow()
            base = sub.expires_at if (pay.purpose == "renewal" and sub.expires_at and as_utc(sub.expires_at) > now) else now
            if base and getattr(base, "tzinfo", None) is None:
                base = base.replace(tzinfo=timezone.utc)
            sub.status = "active"
            sub.starts_at = sub.starts_at or now
            sub.expires_at = (as_utc(base) or now) + timedelta(days=self.settings.subscription_days)
            sub.grace_until = sub.expires_at + timedelta(hours=self.settings.grace_period_hours)
            sub.reminder_7d_sent = sub.reminder_3d_sent = sub.reminder_24h_sent = False
            await s.commit()
            await s.refresh(sub)
            return {"payment": pay, "subscription": sub, "already": False}

    async def process_lifecycle(self, bot: Bot, deploy_engine) -> None:
        async with self.sf() as s:
            subs = (
                await s.execute(
                    select(Subscription)
                    .options(selectinload(Subscription.user), selectinload(Subscription.deployment))
                    .where(Subscription.status.in_(["active", "grace", "expired"]))
                )
            ).scalars().all()
            now = utcnow()
            for sub in subs:
                if not sub.user or not sub.expires_at:
                    continue
                exp = as_utc(sub.expires_at)
                if not exp:
                    continue
                left = exp - now
                days = left.total_seconds() / 86400
                cid = sub.user.telegram_id

                async def note(text: str, _c=cid) -> None:
                    try:
                        await bot.send_message(_c, text)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("notify fail %s: %s", _c, e)

                if sub.status == "active":
                    if 0 < days <= 1 and not sub.reminder_24h_sent:
                        await note("⏰ 24 soat qoldi. /renew")
                        sub.reminder_24h_sent = True
                    elif 1 < days <= 3 and not sub.reminder_3d_sent:
                        await note("⏰ 3 kun qoldi. /renew")
                        sub.reminder_3d_sent = True
                    elif 3 < days <= 7 and not sub.reminder_7d_sent:
                        await note("📅 7 kun qoldi. /renew")
                        sub.reminder_7d_sent = True
                    if left.total_seconds() <= 0:
                        grace = as_utc(sub.grace_until) or exp + timedelta(hours=self.settings.grace_period_hours)
                        if now <= grace:
                            sub.status = "grace"
                            await note("⚠️ Muddati tugadi. /renew")
                        else:
                            sub.status = "expired"
                            if sub.deployment:
                                await deploy_engine.suspend(sub.deployment.id)
                            await note("🛑 Suspend. /renew")
                elif sub.status == "grace":
                    grace = as_utc(sub.grace_until) or exp
                    if now > grace:
                        sub.status = "expired"
                        if sub.deployment:
                            await deploy_engine.suspend(sub.deployment.id)
                        await note("🛑 Suspend. /renew")
                elif sub.status == "expired":
                    last = as_utc(sub.last_daily_reminder_at)
                    if not last or (now - last) >= timedelta(days=1):
                        await note("📢 Suspend. /renew")
                        sub.last_daily_reminder_at = now
                await s.commit()
