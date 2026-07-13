from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from aiogram import Bot
from aiogram.types import LabeledPrice
from sqlalchemy import func, select
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

    def _ref_code(self, telegram_id: int) -> str:
        return f"r{telegram_id}"

    async def ensure_user(
        self,
        telegram_id: int,
        username: Optional[str],
        full_name: str,
        language: str = "uz",
        referral_code: Optional[str] = None,
    ) -> User:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if u:
                u.username = username
                u.full_name = full_name or u.full_name
                if telegram_id in self.settings.admin_telegram_ids:
                    u.role = "admin"
                if not u.referral_code:
                    u.referral_code = self._ref_code(telegram_id)
                # attach referrer only once for brand-new empty field
                if referral_code and not u.referred_by_id and self.settings.referral_enabled:
                    await self._apply_referral(s, u, referral_code)
                await s.commit()
                await s.refresh(u)
                return u

            u = User(
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
                language=language,
                role="admin" if telegram_id in self.settings.admin_telegram_ids else "user",
                referral_code=self._ref_code(telegram_id),
                credit_stars=0,
                referral_paid=False,
            )
            s.add(u)
            await s.flush()
            if referral_code and self.settings.referral_enabled:
                await self._apply_referral(s, u, referral_code)
            await s.commit()
            await s.refresh(u)
            return u

    async def _apply_referral(self, s: AsyncSession, user: User, code: str) -> None:
        code = (code or "").strip()
        if not code or not code.startswith("r"):
            return
        ref = (await s.execute(select(User).where(User.referral_code == code))).scalar_one_or_none()
        if not ref or ref.id == user.id:
            return
        if user.referred_by_id:
            return
        user.referred_by_id = ref.id
        # invitee discount credit
        disc = max(0, int(self.settings.referral_invitee_discount))
        user.credit_stars = int(user.credit_stars or 0) + disc
        logger.info("referral applied user=%s by=%s credit=%s", user.telegram_id, ref.telegram_id, disc)

    def price_for_user(
        self,
        user: Optional[User] = None,
        *,
        days_left: Optional[int] = None,
    ) -> tuple[int, list[str]]:
        """Return final stars price and human labels for discounts."""
        base = self.settings.subscription_price_stars
        price = base
        tags: list[str] = []
        if self.settings.promo_enabled and self.settings.promo_discount_stars > 0:
            off = self.settings.promo_discount_stars
            price = max(50, price - off)
            tags.append(f"🔥 Promo −{off}")
        # New user 24h flash
        if user and user.created_at:
            created = as_utc(user.created_at) or user.created_at
            age_h = (utcnow() - created).total_seconds() / 3600 if created.tzinfo else 999
            if age_h <= float(self.settings.new_user_hours) and self.settings.new_user_discount > 0:
                off = self.settings.new_user_discount
                price = max(50, price - off)
                tags.append(f"⚡ 24s offer −{off}")
        # Keep offer near expiry
        if days_left is not None and days_left <= self.settings.keep_offer_days and days_left >= 0:
            if self.settings.keep_offer_discount > 0:
                off = self.settings.keep_offer_discount
                price = max(50, price - off)
                tags.append(f"🧡 Keep −{off}")
        credit = int(user.credit_stars or 0) if user else 0
        if credit > 0:
            applied = min(credit, max(0, price - 50))
            if applied > 0:
                price -= applied
                tags.append(f"🎁 Bonus −{applied}")
        return price, tags

    async def get_price(self, telegram_id: int) -> tuple[int, list[str]]:
        panel = await self.get_panel(telegram_id)
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            return self.price_for_user(u, days_left=panel.get("days_left"))

    async def payment_history(self, telegram_id: int, limit: int = 15) -> list[dict[str, Any]]:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                return []
            rows = (
                await s.execute(
                    select(Payment).where(Payment.user_id == u.id).order_by(Payment.id.desc()).limit(limit)
                )
            ).scalars().all()
            out = []
            for p in rows:
                dt = as_utc(p.paid_at) or as_utc(p.created_at)
                out.append(
                    {
                        "amount": p.amount_stars,
                        "status": p.status,
                        "purpose": p.purpose,
                        "date": dt.strftime("%Y-%m-%d %H:%M") if dt else "—",
                    }
                )
            return out

    async def grant_bonus_days(self, telegram_id: int, days: int) -> None:
        if days <= 0:
            return
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                return
            sub = (
                await s.execute(
                    select(Subscription)
                    .where(Subscription.user_id == u.id, Subscription.status.in_(["active", "grace"]))
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            if not sub:
                return
            base = as_utc(sub.expires_at) or utcnow()
            sub.expires_at = base + timedelta(days=days)
            sub.status = "active"
            await s.commit()
            logger.info("bonus +%sdays user=%s", days, telegram_id)

    async def referral_stats(self, telegram_id: int) -> dict[str, Any]:
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                return {"code": "", "invites": 0, "credit": 0, "link": ""}
            if not u.referral_code:
                u.referral_code = self._ref_code(telegram_id)
                await s.commit()
            invites = (
                await s.execute(select(func.count()).select_from(User).where(User.referred_by_id == u.id))
            ).scalar() or 0
            bot = self.settings.builder_bot_username or "bot"
            link = f"https://t.me/{bot}?start={u.referral_code}"
            return {
                "code": u.referral_code,
                "invites": invites,
                "credit": int(u.credit_stars or 0),
                "link": link,
            }

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
            grace_days = getattr(self.settings, "grace_period_days", 7) or 7
            sub.grace_until = sub.expires_at + timedelta(days=grace_days)
            sub.price_stars = 0 if not self.settings.payments_enabled else sub.price_stars
            sub.reminder_7d_sent = sub.reminder_3d_sent = sub.reminder_24h_sent = False
            sub.last_daily_reminder_at = None
            await s.commit()
            await s.refresh(sub)
            logger.info("test sub granted user=%s exp=%s", telegram_id, sub.expires_at)
            return {"user": u, "subscription": sub}

    async def create_invoice_payload(self, telegram_id: int, purpose: str = "new_subscription") -> tuple[str, int]:
        """Returns (payload, amount_stars)."""
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                raise ValueError("User topilmadi")
            # days_left for keep-offer
            days_left = None
            sub_tmp = (
                await s.execute(
                    select(Subscription)
                    .where(Subscription.user_id == u.id)
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            if sub_tmp and sub_tmp.expires_at:
                exp = as_utc(sub_tmp.expires_at)
                if exp:
                    days_left = max(0, int((exp - utcnow()).total_seconds() // 86400))
            amount, _tags = self.price_for_user(u, days_left=days_left)
            sub = (
                await s.execute(
                    select(Subscription)
                    .where(Subscription.user_id == u.id, Subscription.status.in_(["active", "grace", "pending"]))
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            if not sub or sub.status in {"expired", "cancelled"}:
                sub = Subscription(user_id=u.id, price_stars=amount)
                s.add(sub)
                await s.flush()
            payload = f"sub:{sub.id}:u:{u.id}:p:{purpose}:a:{amount}:{int(utcnow().timestamp())}"
            s.add(
                Payment(
                    user_id=u.id,
                    subscription_id=sub.id,
                    amount_stars=amount,
                    purpose=purpose,
                    payload=payload,
                    status="pending",
                )
            )
            await s.commit()
            return payload, amount

    async def send_stars_invoice(self, bot: Bot, chat_id: int, payload: str, amount: Optional[int] = None) -> None:
        stars = amount or self.settings.effective_price
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"{self.settings.brand_name} · Premium",
            description=(
                f"Mafia bot hosting {self.settings.subscription_days} kun · "
                f"avtomatik deploy, backup, support"
            ),
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{self.settings.subscription_days} kun hosting",
                    amount=stars,
                )
            ],
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
            grace_days = getattr(self.settings, "grace_period_days", 7) or 7
            sub.grace_until = sub.expires_at + timedelta(days=grace_days)
            sub.reminder_7d_sent = sub.reminder_3d_sent = sub.reminder_24h_sent = False
            sub.last_daily_reminder_at = None

            # spend credit stars used on this payment
            payer = await s.get(User, pay.user_id)
            if payer and pay.amount_stars < self.settings.subscription_price_stars:
                used = self.settings.subscription_price_stars - pay.amount_stars
                # approximate: clear applied credit
                if self.settings.promo_enabled:
                    used = max(0, used - self.settings.promo_discount_stars)
                if used > 0 and (payer.credit_stars or 0) > 0:
                    payer.credit_stars = max(0, int(payer.credit_stars) - used)

            # reward referrer once
            if payer and not payer.referral_paid and payer.referred_by_id:
                ref = await s.get(User, payer.referred_by_id)
                if ref:
                    ref_sub = (
                        await s.execute(
                            select(Subscription)
                            .where(Subscription.user_id == ref.id, Subscription.status.in_(["active", "grace"]))
                            .order_by(Subscription.id.desc())
                        )
                    ).scalars().first()
                    bonus = int(self.settings.referral_reward_days)
                    if ref_sub and ref_sub.expires_at:
                        base = as_utc(ref_sub.expires_at) or utcnow()
                        ref_sub.expires_at = base + timedelta(days=bonus)
                        ref_sub.status = "active"
                    payer.referral_paid = True
                    logger.info("referral reward +%sdays to user_id=%s", bonus, ref.id)

            await s.commit()
            await s.refresh(sub)
            return {"payment": pay, "subscription": sub, "already": False, "payer_id": pay.user_id}

    async def admin_overview(self) -> dict[str, Any]:
        async with self.sf() as s:
            users = (await s.execute(select(func.count()).select_from(User))).scalar() or 0
            deps = (await s.execute(select(Deployment).where(Deployment.status != "deleted"))).scalars().all()
            pays = (
                await s.execute(select(Payment).where(Payment.status == "success"))
            ).scalars().all()
            stars = sum(p.amount_stars for p in pays)
            by_status: dict[str, int] = {}
            for d in deps:
                by_status[d.status] = by_status.get(d.status, 0) + 1
            active_subs = (
                await s.execute(select(func.count()).select_from(Subscription).where(Subscription.status == "active"))
            ).scalar() or 0
            return {
                "users": users,
                "deployments": len(deps),
                "running": by_status.get("running", 0),
                "stopped": by_status.get("stopped", 0),
                "suspended": by_status.get("suspended", 0),
                "failed": by_status.get("failed", 0),
                "provisioning": by_status.get("provisioning", 0),
                "active_subs": active_subs,
                "payments": len(pays),
                "stars": stars,
                "deps": deps,
            }

    async def list_users(self, limit: int = 30) -> list[User]:
        async with self.sf() as s:
            return list(
                (
                    await s.execute(select(User).order_by(User.id.desc()).limit(limit))
                ).scalars().all()
            )

    async def get_deployment(self, dep_id: int) -> Optional[Deployment]:
        async with self.sf() as s:
            return (
                await s.execute(
                    select(Deployment)
                    .options(selectinload(Deployment.user), selectinload(Deployment.subscription))
                    .where(Deployment.id == dep_id)
                )
            ).scalar_one_or_none()

    async def process_lifecycle(self, bot: Bot, deploy_engine) -> None:
        from builder.copy import remind_24h, remind_3d, remind_7d, remind_expired, remind_grace_daily

        grace_days = getattr(self.settings, "grace_period_days", 7) or 7
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
                dep = sub.deployment

                async def note(text: str, _c=cid) -> None:
                    try:
                        await bot.send_message(_c, text)
                    except Exception as e:  # noqa: BLE001
                        logger.warning("notify fail %s: %s", _c, e)

                if sub.status == "active":
                    if 0 < days <= 1 and not sub.reminder_24h_sent:
                        await note(remind_24h(self.settings))
                        sub.reminder_24h_sent = True
                    elif 1 < days <= 3 and not sub.reminder_3d_sent:
                        await note(remind_3d(self.settings))
                        sub.reminder_3d_sent = True
                    elif 3 < days <= 7 and not sub.reminder_7d_sent:
                        await note(remind_7d(self.settings))
                        sub.reminder_7d_sent = True

                    # Expire day: suspend immediately + 7-day grace before purge
                    if left.total_seconds() <= 0:
                        sub.status = "grace"
                        sub.grace_until = exp + timedelta(days=grace_days)
                        if dep and dep.status not in {"deleted", "suspended"}:
                            await deploy_engine.suspend(dep.id)
                        await note(remind_expired(self.settings))

                elif sub.status == "grace":
                    grace_until = as_utc(sub.grace_until) or exp + timedelta(days=grace_days)
                    remaining_grace = grace_until - now
                    if remaining_grace.total_seconds() <= 0:
                        sub.status = "expired"
                        if dep and dep.status != "deleted":
                            await deploy_engine.purge(dep.id)
                        await note(
                            "<b>Bot removed</b>\n\n"
                            "The 7-day grace period ended without payment.\n"
                            "Your deployment was permanently deleted.\n"
                            "Create a new bot anytime from the menu."
                        )
                    else:
                        last = as_utc(sub.last_daily_reminder_at)
                        if not last or (now - last) >= timedelta(days=1):
                            dleft = max(1, int(remaining_grace.total_seconds() // 86400))
                            await note(remind_grace_daily(dleft))
                            sub.last_daily_reminder_at = now

                elif sub.status == "expired":
                    # ensure purged if still present
                    if dep and dep.status not in {"deleted"}:
                        await deploy_engine.purge(dep.id)

                await s.commit()
