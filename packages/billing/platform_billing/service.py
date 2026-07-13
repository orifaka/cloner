from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from aiogram import Bot
from aiogram.types import LabeledPrice
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform_core.config import Settings
from platform_core.enums import (
    DeploymentStatus,
    NotificationType,
    PaymentPurpose,
    PaymentStatus,
    SubscriptionStatus,
)
from platform_core.repositories import (
    DeploymentRepository,
    LogRepository,
    NotificationRepository,
    PaymentRepository,
    SubscriptionRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """Normalize DB datetimes (sqlite may return naive)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class BillingService:
    """Telegram Stars payments + subscription lifecycle."""

    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.session_factory = session_factory

    async def ensure_user(
        self,
        telegram_id: int,
        username: Optional[str],
        full_name: str,
        language: str = "uz",
    ):
        async with self.session_factory() as session:
            repo = UserRepository(session)
            is_admin = telegram_id in self.settings.admin_telegram_ids
            return await repo.get_or_create(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                language=language,
                is_admin=is_admin,
            )

    async def get_user_panel(self, telegram_id: int) -> dict:
        async with self.session_factory() as session:
            user = await UserRepository(session).get_by_telegram_id(telegram_id)
            if not user:
                return {"user": None}
            sub = await SubscriptionRepository(session).get_active_for_user(user.id)
            dep = await DeploymentRepository(session).get_by_user(user.id)
            days_left = None
            exp = as_utc(sub.expires_at) if sub else None
            if sub and exp:
                delta = exp - utcnow()
                days_left = max(0, int(delta.total_seconds() // 86400))
            return {
                "user": user,
                "subscription": sub,
                "deployment": dep,
                "days_left": days_left,
            }

    async def grant_test_subscription(self, telegram_id: int) -> dict:
        """Activate free subscription when PAYMENTS_ENABLED=false (testing only)."""
        async with self.session_factory() as session:
            users = UserRepository(session)
            subs = SubscriptionRepository(session)
            logs = LogRepository(session)
            user = await users.get_by_telegram_id(telegram_id)
            if not user:
                raise ValueError("User not found")

            sub = await subs.get_active_for_user(user.id)
            now = utcnow()
            if not sub or sub.status in {
                SubscriptionStatus.EXPIRED.value,
                SubscriptionStatus.CANCELLED.value,
            }:
                sub = await subs.create(
                    user_id=user.id,
                    price_stars=0,
                )

            sub.status = SubscriptionStatus.ACTIVE.value
            sub.starts_at = sub.starts_at or now
            sub.expires_at = now + timedelta(days=self.settings.subscription_days)
            sub.grace_until = sub.expires_at + timedelta(hours=self.settings.grace_period_hours)
            sub.reminder_7d_sent = False
            sub.reminder_3d_sent = False
            sub.reminder_24h_sent = False
            sub.expired_notice_sent = False
            sub.price_stars = 0
            await subs.save(sub)
            await logs.activity(
                action="test_subscription_granted",
                user_id=user.id,
                detail=f"expires_at={sub.expires_at.isoformat()}",
            )
            return {"user": user, "subscription": sub}

    async def create_invoice_payload(self, telegram_id: int, purpose: str = PaymentPurpose.NEW_SUBSCRIPTION.value) -> str:
        async with self.session_factory() as session:
            user = await UserRepository(session).get_by_telegram_id(telegram_id)
            if not user:
                raise ValueError("User not found")

            existing_dep = await DeploymentRepository(session).get_by_user(user.id)
            if purpose == PaymentPurpose.NEW_SUBSCRIPTION.value and existing_dep:
                if existing_dep.status not in {
                    DeploymentStatus.DELETED.value,
                    DeploymentStatus.FAILED.value,
                }:
                    # If already has bot, treat as renewal unless deleted
                    purpose = PaymentPurpose.RENEWAL.value

            sub = await SubscriptionRepository(session).get_active_for_user(user.id)
            if not sub or sub.status in {
                SubscriptionStatus.EXPIRED.value,
                SubscriptionStatus.CANCELLED.value,
            }:
                sub = await SubscriptionRepository(session).create(
                    user_id=user.id,
                    price_stars=self.settings.subscription_price_stars,
                )
            payload = f"sub:{sub.id}:u:{user.id}:p:{purpose}:{int(utcnow().timestamp())}"
            await PaymentRepository(session).create(
                user_id=user.id,
                subscription_id=sub.id,
                amount_stars=self.settings.subscription_price_stars,
                purpose=purpose,
                payload=payload,
            )
            await LogRepository(session).activity(
                action="invoice_created",
                user_id=user.id,
                detail=payload,
            )
            return payload

    async def send_stars_invoice(self, bot: Bot, chat_id: int, payload: str) -> None:
        prices = [
            LabeledPrice(
                label=f"{self.settings.brand_name} — 30 kun",
                amount=self.settings.subscription_price_stars,
            )
        ]
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"{self.settings.brand_name} obuna",
            description=(
                f"Mafia bot avtomatik hosting — {self.settings.subscription_days} kun.\n"
                f"Narx: {self.settings.subscription_price_stars} Telegram Stars.\n"
                "To'lovdan so'ng BotFather token yuborasiz, bot o'zi deploy qiladi."
            ),
            payload=payload,
            provider_token="",  # Stars
            currency="XTR",
            prices=prices,
        )

    async def activate_subscription_from_payment(
        self,
        payload: str,
        telegram_payment_charge_id: Optional[str],
        provider_payment_charge_id: Optional[str],
        raw: Optional[dict] = None,
    ) -> dict:
        async with self.session_factory() as session:
            payments = PaymentRepository(session)
            subs = SubscriptionRepository(session)
            logs = LogRepository(session)

            payment = await payments.get_by_payload(payload)
            if not payment:
                raise ValueError("Payment not found for payload")
            if payment.status == PaymentStatus.SUCCESS.value:
                sub = await subs.get(payment.subscription_id or 0)
                return {"payment": payment, "subscription": sub, "already": True}

            payment = await payments.mark_success(
                payment,
                telegram_payment_charge_id=telegram_payment_charge_id,
                provider_payment_charge_id=provider_payment_charge_id,
                raw_json=json.dumps(raw, ensure_ascii=False) if raw else None,
            )
            sub = await subs.get(payment.subscription_id or 0)
            if not sub:
                raise ValueError("Subscription missing")

            now = utcnow()
            if (
                payment.purpose == PaymentPurpose.RENEWAL.value
                and sub.expires_at
                and sub.expires_at > now
            ):
                base = sub.expires_at
            else:
                base = now

            sub.status = SubscriptionStatus.ACTIVE.value
            sub.starts_at = sub.starts_at or now
            sub.expires_at = base + timedelta(days=self.settings.subscription_days)
            sub.grace_until = sub.expires_at + timedelta(hours=self.settings.grace_period_hours)
            sub.reminder_7d_sent = False
            sub.reminder_3d_sent = False
            sub.reminder_24h_sent = False
            sub.expired_notice_sent = False
            sub.last_daily_reminder_at = None
            await subs.save(sub)

            await logs.activity(
                action="subscription_activated",
                user_id=sub.user_id,
                detail=f"expires_at={sub.expires_at.isoformat()}",
            )
            await logs.audit(
                action="payment_success",
                entity_type="payment",
                entity_id=str(payment.id),
                detail=f"stars={payment.amount_stars}",
            )
            return {"payment": payment, "subscription": sub, "already": False}

    async def process_lifecycle(self, bot: Bot, deploy_engine) -> None:
        """Reminders, grace, suspend, daily expired notices."""
        async with self.session_factory() as session:
            subs_repo = SubscriptionRepository(session)
            notes = NotificationRepository(session)
            logs = LogRepository(session)
            items = await subs_repo.list_for_lifecycle()
            now = utcnow()

            for sub in items:
                if not sub.user or not sub.expires_at:
                    continue
                expires = as_utc(sub.expires_at)
                if not expires:
                    continue
                remaining = expires - now
                days = remaining.total_seconds() / 86400
                chat_id = sub.user.telegram_id

                async def _notify(ntype: str, text: str, _uid=sub.user_id, _cid=chat_id) -> None:
                    try:
                        await bot.send_message(_cid, text)
                        await notes.create(_uid, ntype, ntype, text)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("notify failed user=%s: %s", _cid, exc)

                if sub.status == SubscriptionStatus.ACTIVE.value:
                    if 0 < days <= 1 and not sub.reminder_24h_sent:
                        await _notify(
                            NotificationType.REMINDER_24H.value,
                            "⏰ 24 soat qoldi. /renew",
                        )
                        sub.reminder_24h_sent = True
                        await subs_repo.save(sub)
                    elif 1 < days <= 3 and not sub.reminder_3d_sent:
                        await _notify(NotificationType.REMINDER_3D.value, "⏰ 3 kun qoldi. /renew")
                        sub.reminder_3d_sent = True
                        await subs_repo.save(sub)
                    elif 3 < days <= 7 and not sub.reminder_7d_sent:
                        await _notify(NotificationType.REMINDER_7D.value, "📅 7 kun qoldi. /renew")
                        sub.reminder_7d_sent = True
                        await subs_repo.save(sub)

                    if remaining.total_seconds() <= 0:
                        grace_until = as_utc(sub.grace_until) or (
                            expires + timedelta(hours=self.settings.grace_period_hours)
                        )
                        if now <= grace_until:
                            sub.status = SubscriptionStatus.GRACE.value
                            await subs_repo.save(sub)
                            await _notify(
                                NotificationType.EXPIRED.value,
                                "⚠️ Muddati tugadi. Grace: /renew",
                            )
                        else:
                            sub.status = SubscriptionStatus.EXPIRED.value
                            await subs_repo.save(sub)
                            if sub.deployment:
                                await deploy_engine.suspend(sub.deployment.id)
                            await _notify(
                                NotificationType.SUSPENDED.value,
                                "🛑 Suspend. /renew",
                            )

                elif sub.status == SubscriptionStatus.GRACE.value:
                    grace_until = as_utc(sub.grace_until) or expires
                    if now > grace_until:
                        sub.status = SubscriptionStatus.EXPIRED.value
                        await subs_repo.save(sub)
                        if sub.deployment:
                            await deploy_engine.suspend(sub.deployment.id)
                        await _notify(NotificationType.SUSPENDED.value, "🛑 Suspend. /renew")

                elif sub.status == SubscriptionStatus.EXPIRED.value:
                    last = as_utc(sub.last_daily_reminder_at)
                    if not last or (now - last) >= timedelta(days=1):
                        await _notify(
                            NotificationType.DAILY_EXPIRED.value,
                            "📢 Suspend. /renew",
                        )
                        sub.last_daily_reminder_at = now
                        await subs_repo.save(sub)

                await logs.activity(
                    action="lifecycle_tick",
                    user_id=sub.user_id,
                    detail=f"status={sub.status}",
                )
