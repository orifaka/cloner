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

# Telegram Stars invoice minimum
MIN_STARS = 1
# Commercial floor after global promo (before personal credit)
MIN_PROMO_PRICE = 50


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class BillingService:
    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        store: Any = None,
    ) -> None:
        self.settings = settings
        self.sf = session_factory
        self.store = store

    def _ref_code(self, telegram_id: int) -> str:
        return f"r{telegram_id}"

    # ── platform config (store-backed) ──────────────────

    async def base_price(self) -> int:
        if self.store:
            try:
                return await self.store.price_stars()
            except Exception:  # noqa: BLE001
                pass
        return self.settings.subscription_price_stars

    async def sub_days(self) -> int:
        if self.store:
            try:
                return await self.store.sub_days()
            except Exception:  # noqa: BLE001
                pass
        return self.settings.subscription_days

    async def grace_days(self) -> int:
        return max(1, int(getattr(self.settings, "grace_period_days", 7) or 7))

    async def promo_discount(self) -> tuple[bool, int]:
        if self.store:
            try:
                cfg = await self.store.promo_cfg()
                return bool(cfg["enabled"]), int(cfg["discount"])
            except Exception:  # noqa: BLE001
                pass
        return self.settings.promo_enabled, self.settings.promo_discount_stars

    async def payments_enabled(self) -> bool:
        if self.store:
            try:
                return await self.store.payments_on()
            except Exception:  # noqa: BLE001
                pass
        return self.settings.payments_enabled

    # ── users ───────────────────────────────────────────

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
        if not ref or ref.id == user.id or user.referred_by_id:
            return
        user.referred_by_id = ref.id
        disc = max(0, int(self.settings.referral_invitee_discount))
        user.credit_stars = int(user.credit_stars or 0) + disc
        logger.info("referral applied user=%s by=%s credit=%s", user.telegram_id, ref.telegram_id, disc)

    # ── pricing ─────────────────────────────────────────

    async def price_for_user(
        self,
        user: Optional[User] = None,
        *,
        days_left: Optional[int] = None,
    ) -> tuple[int, list[str], int]:
        """
        Final stars to charge, discount labels, credit applied.
        Personal credit may reduce price to 0 (free activation).
        """
        base = await self.base_price()
        price = base
        tags: list[str] = []
        promo_on, promo_off = await self.promo_discount()
        if promo_on and promo_off > 0:
            price = max(MIN_PROMO_PRICE, price - promo_off)
            tags.append(f"🔥 Promo −{promo_off}")

        if user and user.created_at:
            created = as_utc(user.created_at) or user.created_at
            try:
                age_h = (utcnow() - created).total_seconds() / 3600
            except Exception:  # noqa: BLE001
                age_h = 999
            if age_h <= float(self.settings.new_user_hours) and self.settings.new_user_discount > 0:
                off = self.settings.new_user_discount
                price = max(0, price - off)
                tags.append(f"⚡ 24s −{off}")

        if days_left is not None and 0 <= days_left <= self.settings.keep_offer_days:
            if self.settings.keep_offer_discount > 0:
                off = self.settings.keep_offer_discount
                price = max(0, price - off)
                tags.append(f"🧡 Keep −{off}")

        credit = int(user.credit_stars or 0) if user else 0
        credit_applied = 0
        if credit > 0 and price > 0:
            credit_applied = min(credit, price)
            price -= credit_applied
            tags.append(f"🎁 Bonus −{credit_applied}")

        return max(0, int(price)), tags, int(credit_applied)

    async def get_price(self, telegram_id: int) -> tuple[int, list[str]]:
        panel = await self.get_panel(telegram_id)
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            price, tags, _ = await self.price_for_user(u, days_left=panel.get("days_left"))
            return price, tags

    # ── panel / history ─────────────────────────────────

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
            gd = await self.grace_days()
            sub.grace_until = sub.expires_at + timedelta(days=gd)
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
            # Prefer active/grace/pending, else latest for display
            sub = (
                await s.execute(
                    select(Subscription)
                    .options(selectinload(Subscription.deployment))
                    .where(Subscription.user_id == u.id, Subscription.status.in_(["active", "grace", "pending"]))
                    .order_by(Subscription.id.desc())
                )
            ).scalars().first()
            if not sub:
                sub = (
                    await s.execute(
                        select(Subscription)
                        .options(selectinload(Subscription.deployment))
                        .where(Subscription.user_id == u.id)
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
            if exp and sub and sub.status in {"active", "grace", "pending"}:
                days = max(0, int((exp - utcnow()).total_seconds() // 86400))
            elif exp and sub and sub.status == "expired":
                days = 0
            return {
                "user": u,
                "subscription": sub,
                "deployment": dep,
                "days_left": days,
                "credit": int(u.credit_stars or 0),
            }

    def has_active_sub(self, sub: Optional[Subscription]) -> bool:
        return bool(sub and sub.status in {"active", "grace"})

    # ── test mode only ──────────────────────────────────

    async def grant_test_subscription(self, telegram_id: int) -> dict[str, Any]:
        """Free subscription — ONLY when payments are disabled (test mode)."""
        if await self.payments_enabled():
            raise ValueError("To‘lov yoqilgan — bepul obuna berilmaydi")
        days = await self.sub_days()
        gd = await self.grace_days()
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                raise ValueError("User topilmadi")
            sub = (
                await s.execute(
                    select(Subscription).where(Subscription.user_id == u.id).order_by(Subscription.id.desc())
                )
            ).scalars().first()
            now = utcnow()
            if not sub or sub.status in {"expired", "cancelled"}:
                sub = Subscription(
                    user_id=u.id,
                    price_stars=0,
                    plan_code="test_free",
                    auto_renew=False,
                    expired_notice_sent=False,
                )
                s.add(sub)
            sub.status = "active"
            sub.plan_code = "test_free"
            sub.starts_at = sub.starts_at or now
            sub.expires_at = now + timedelta(days=days)
            sub.grace_until = sub.expires_at + timedelta(days=gd)
            sub.price_stars = 0
            sub.reminder_7d_sent = sub.reminder_3d_sent = sub.reminder_24h_sent = False
            sub.expired_notice_sent = False
            sub.last_daily_reminder_at = None
            await s.commit()
            await s.refresh(sub)
            logger.info("test sub granted user=%s exp=%s", telegram_id, sub.expires_at)
            return {"user": u, "subscription": sub}

    # ── checkout ────────────────────────────────────────

    async def _days_left_for_user(self, s: AsyncSession, user_id: int) -> Optional[int]:
        sub = (
            await s.execute(
                select(Subscription)
                .where(Subscription.user_id == user_id, Subscription.status.in_(["active", "grace"]))
                .order_by(Subscription.id.desc())
            )
        ).scalars().first()
        if not sub or not sub.expires_at:
            return None
        exp = as_utc(sub.expires_at)
        if not exp:
            return None
        return max(0, int((exp - utcnow()).total_seconds() // 86400))

    async def _get_or_create_sub(
        self,
        s: AsyncSession,
        user: User,
        amount: int,
        purpose: str,
    ) -> Subscription:
        sub = (
            await s.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id, Subscription.status.in_(["active", "grace", "pending"]))
                .order_by(Subscription.id.desc())
            )
        ).scalars().first()
        if not sub or sub.status in {"expired", "cancelled"}:
            sub = Subscription(
                user_id=user.id,
                price_stars=amount,
                plan_code="monthly_stars",
                status="pending",
                auto_renew=False,
                expired_notice_sent=False,
            )
            s.add(sub)
            await s.flush()
        else:
            # keep pending/active for renewal
            if sub.status == "expired":
                sub.status = "pending"
            sub.price_stars = amount if amount > 0 else sub.price_stars
            sub.plan_code = sub.plan_code or "monthly_stars"
        return sub

    async def start_checkout(self, telegram_id: int, purpose: str = "new_subscription") -> dict[str, Any]:
        """
        Production checkout entry.
        Returns:
          free=True  → activated via credit, subscription ready
          free=False → payload + amount for Stars invoice
        """
        if not await self.payments_enabled():
            raise ValueError("To‘lov o‘chiq (test rejim)")

        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                raise ValueError("User topilmadi — /start bosing")

            days_left = await self._days_left_for_user(s, u.id)
            amount, tags, credit_applied = await self.price_for_user(u, days_left=days_left)
            base = await self.base_price()
            days = await self.sub_days()
            gd = await self.grace_days()

            # Free path: full credit cover
            if amount <= 0 and credit_applied > 0:
                sub = await self._get_or_create_sub(s, u, 0, purpose)
                meta = {
                    "credit_applied": credit_applied,
                    "base_price": base,
                    "final_price": 0,
                    "tags": tags,
                    "days": days,
                }
                pay = Payment(
                    user_id=u.id,
                    subscription_id=sub.id,
                    amount_stars=0,
                    purpose=purpose,
                    payload=f"credit:{sub.id}:u:{u.id}:p:{purpose}:{int(utcnow().timestamp())}",
                    status="success",
                    paid_at=utcnow(),
                    raw_json=json.dumps(meta, ensure_ascii=False),
                )
                s.add(pay)
                # spend credit
                u.credit_stars = max(0, int(u.credit_stars or 0) - credit_applied)
                await self._activate_sub(s, sub, purpose=purpose, days=days, grace_days=gd, price_stars=0)
                await self._maybe_referral_reward(s, u)
                await s.commit()
                await s.refresh(sub)
                logger.info("free credit checkout user=%s credit=%s", telegram_id, credit_applied)
                return {
                    "free": True,
                    "subscription": sub,
                    "amount": 0,
                    "credit_applied": credit_applied,
                    "tags": tags,
                }

            # Paid Stars invoice (min 1)
            charge = max(MIN_STARS, amount)
            # if amount was 0 with no credit, still charge base (edge case)
            if amount <= 0 and credit_applied == 0:
                charge = max(MIN_STARS, base)
                credit_applied = 0

            sub = await self._get_or_create_sub(s, u, charge, purpose)
            meta = {
                "credit_applied": credit_applied,
                "base_price": base,
                "final_price": charge,
                "tags": tags,
                "days": days,
            }
            payload = f"sub:{sub.id}:u:{u.id}:p:{purpose}:a:{charge}:{int(utcnow().timestamp())}"
            s.add(
                Payment(
                    user_id=u.id,
                    subscription_id=sub.id,
                    amount_stars=charge,
                    purpose=purpose,
                    payload=payload,
                    status="pending",
                    raw_json=json.dumps(meta, ensure_ascii=False),
                )
            )
            # Reserve credit only after successful payment — stored in raw_json
            await s.commit()
            logger.info(
                "invoice ready user=%s amount=%s credit=%s purpose=%s",
                telegram_id,
                charge,
                credit_applied,
                purpose,
            )
            return {
                "free": False,
                "payload": payload,
                "amount": charge,
                "credit_applied": credit_applied,
                "tags": tags,
                "days": days,
            }

    async def create_invoice_payload(
        self, telegram_id: int, purpose: str = "new_subscription"
    ) -> tuple[str, int]:
        """Legacy helper: returns (payload, amount). Raises if free checkout."""
        res = await self.start_checkout(telegram_id, purpose)
        if res.get("free"):
            # Should not create invoice — caller should use start_checkout
            raise ValueError("FREE_CHECKOUT")
        return res["payload"], int(res["amount"])

    async def send_stars_invoice(
        self,
        bot: Bot,
        chat_id: int,
        payload: str,
        amount: Optional[int] = None,
        days: Optional[int] = None,
    ) -> None:
        stars = max(MIN_STARS, int(amount or await self.base_price()))
        period = days if days is not None else await self.sub_days()
        await bot.send_invoice(
            chat_id=chat_id,
            title=f"{self.settings.brand_name} · Premium",
            description=(
                f"Mafia bot hosting {period} kun · "
                f"avtomatik deploy, backup, support"
            ),
            payload=payload,
            provider_token="",
            currency="XTR",
            prices=[
                LabeledPrice(
                    label=f"{period} kun hosting",
                    amount=stars,
                )
            ],
        )

    async def validate_checkout(self, payload: str, total_amount: int) -> tuple[bool, str]:
        """pre_checkout_query validation."""
        if not await self.payments_enabled():
            return False, "To‘lov vaqtincha o‘chiq."
        async with self.sf() as s:
            pay = (await s.execute(select(Payment).where(Payment.payload == payload))).scalar_one_or_none()
            if not pay:
                return False, "To‘lov topilmadi. Qayta urinib ko‘ring."
            if pay.status == "success":
                return False, "Bu to‘lov allaqachon qabul qilingan."
            if pay.status not in {"pending"}:
                return False, "To‘lov holati noto‘g‘ri."
            if int(pay.amount_stars) != int(total_amount):
                return False, "Summa mos emas. Yangi invoice oling."
            # expire stale invoices (>2 hours)
            created = as_utc(pay.created_at)
            if created and (utcnow() - created) > timedelta(hours=2):
                pay.status = "expired"
                await s.commit()
                return False, "Invoice muddati tugagan. Yangi to‘lov boshlang."
            return True, ""

    async def _activate_sub(
        self,
        s: AsyncSession,
        sub: Subscription,
        *,
        purpose: str,
        days: int,
        grace_days: int,
        price_stars: int,
    ) -> None:
        now = utcnow()
        exp = as_utc(sub.expires_at)
        # Extend from current expiry if still valid (renewal / grace with leftover)
        if purpose in {"renewal", "reactivate"} and exp and exp > now:
            base = exp
        elif purpose == "renewal" and exp and exp <= now:
            # expired or grace — start fresh from now
            base = now
        else:
            base = now
        sub.status = "active"
        sub.starts_at = sub.starts_at or now
        sub.expires_at = base + timedelta(days=days)
        sub.grace_until = sub.expires_at + timedelta(days=grace_days)
        sub.price_stars = price_stars
        sub.plan_code = sub.plan_code or "monthly_stars"
        sub.reminder_7d_sent = False
        sub.reminder_3d_sent = False
        sub.reminder_24h_sent = False
        sub.expired_notice_sent = False
        sub.last_daily_reminder_at = None

    async def _maybe_referral_reward(self, s: AsyncSession, payer: User) -> None:
        if not payer or payer.referral_paid or not payer.referred_by_id:
            return
        ref = await s.get(User, payer.referred_by_id)
        if not ref:
            return
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
            gd = await self.grace_days()
            ref_sub.grace_until = ref_sub.expires_at + timedelta(days=gd)
        payer.referral_paid = True
        logger.info("referral reward +%sdays to user_id=%s", bonus, ref.id)

    async def activate_from_payment(
        self,
        payload: str,
        charge_id: Optional[str],
        provider_id: Optional[str],
    ) -> dict[str, Any]:
        days = await self.sub_days()
        gd = await self.grace_days()
        async with self.sf() as s:
            pay = (await s.execute(select(Payment).where(Payment.payload == payload))).scalar_one_or_none()
            if not pay:
                raise ValueError("Payment topilmadi")
            if pay.status == "success":
                sub = await s.get(Subscription, pay.subscription_id) if pay.subscription_id else None
                return {"payment": pay, "subscription": sub, "already": True}

            pay.status = "success"
            pay.telegram_payment_charge_id = charge_id
            pay.provider_payment_charge_id = provider_id
            pay.paid_at = utcnow()

            meta: dict[str, Any] = {}
            if pay.raw_json:
                try:
                    meta = json.loads(pay.raw_json)
                except Exception:  # noqa: BLE001
                    meta = {}
            credit_applied = int(meta.get("credit_applied") or 0)
            period = int(meta.get("days") or days)

            sub = await s.get(Subscription, pay.subscription_id) if pay.subscription_id else None
            if not sub:
                raise ValueError("Subscription yo'q")

            purpose = pay.purpose or "new_subscription"
            await self._activate_sub(
                s,
                sub,
                purpose=purpose,
                days=period,
                grace_days=gd,
                price_stars=int(pay.amount_stars),
            )

            payer = await s.get(User, pay.user_id)
            if payer and credit_applied > 0:
                payer.credit_stars = max(0, int(payer.credit_stars or 0) - credit_applied)
                logger.info(
                    "credit spent user_id=%s applied=%s left=%s",
                    payer.id,
                    credit_applied,
                    payer.credit_stars,
                )

            if payer:
                await self._maybe_referral_reward(s, payer)

            await s.commit()
            await s.refresh(sub)
            logger.info(
                "payment OK payload=%s amount=%s purpose=%s exp=%s",
                payload[:40],
                pay.amount_stars,
                purpose,
                sub.expires_at,
            )
            return {
                "payment": pay,
                "subscription": sub,
                "already": False,
                "payer_id": pay.user_id,
                "purpose": purpose,
            }

    # ── admin ───────────────────────────────────────────

    async def admin_overview(self) -> dict[str, Any]:
        async with self.sf() as s:
            users = (await s.execute(select(func.count()).select_from(User))).scalar() or 0
            deps = (await s.execute(select(Deployment).where(Deployment.status != "deleted"))).scalars().all()
            pays = (await s.execute(select(Payment).where(Payment.status == "success"))).scalars().all()
            stars = sum(p.amount_stars for p in pays)
            by_status: dict[str, int] = {}
            for d in deps:
                by_status[d.status] = by_status.get(d.status, 0) + 1
            active_subs = (
                await s.execute(
                    select(func.count()).select_from(Subscription).where(Subscription.status == "active")
                )
            ).scalar() or 0
            pending_pays = (
                await s.execute(
                    select(func.count()).select_from(Payment).where(Payment.status == "pending")
                )
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
                "pending_pays": pending_pays,
                "deps": deps,
            }

    async def list_users(self, limit: int = 30) -> list[User]:
        async with self.sf() as s:
            return list((await s.execute(select(User).order_by(User.id.desc()).limit(limit))).scalars().all())

    async def get_deployment(self, dep_id: int) -> Optional[Deployment]:
        async with self.sf() as s:
            return (
                await s.execute(
                    select(Deployment)
                    .options(selectinload(Deployment.user), selectinload(Deployment.subscription))
                    .where(Deployment.id == dep_id)
                )
            ).scalar_one_or_none()

    # ── lifecycle ───────────────────────────────────────

    async def process_lifecycle(self, bot: Bot, deploy_engine) -> None:
        from builder.copy import remind_24h, remind_3d, remind_7d, remind_expired, remind_grace_daily

        grace_days = await self.grace_days()
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

                    if left.total_seconds() <= 0:
                        sub.status = "grace"
                        sub.grace_until = exp + timedelta(days=grace_days)
                        if dep and dep.status not in {"deleted", "suspended"}:
                            try:
                                await deploy_engine.suspend(dep.id)
                            except Exception:  # noqa: BLE001
                                logger.exception("suspend fail dep=%s", dep.id)
                        await note(remind_expired(self.settings))

                elif sub.status == "grace":
                    grace_until = as_utc(sub.grace_until) or exp + timedelta(days=grace_days)
                    remaining_grace = grace_until - now
                    if remaining_grace.total_seconds() <= 0:
                        sub.status = "expired"
                        if dep and dep.status != "deleted":
                            try:
                                await deploy_engine.purge(dep.id)
                            except Exception:  # noqa: BLE001
                                logger.exception("purge fail dep=%s", dep.id)
                        await note(
                            "🗑 <b>Bot o‘chirildi</b>\n\n"
                            f"{grace_days} kunlik grace muddati to‘lovsiz tugadi.\n"
                            "Deployment butunlay o‘chirildi.\n"
                            "Menyudan yangi bot ochishingiz mumkin."
                        )
                    else:
                        last = as_utc(sub.last_daily_reminder_at)
                        if not last or (now - last) >= timedelta(days=1):
                            dleft = max(1, int(remaining_grace.total_seconds() // 86400))
                            await note(remind_grace_daily(dleft))
                            sub.last_daily_reminder_at = now

                elif sub.status == "expired":
                    if dep and dep.status not in {"deleted"}:
                        try:
                            await deploy_engine.purge(dep.id)
                        except Exception:  # noqa: BLE001
                            logger.exception("purge expired dep=%s", dep.id)

                await s.commit()

