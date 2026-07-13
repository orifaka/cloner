"""Runtime platform settings + promo codes service."""

from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from builder.config import Settings, clear_settings_cache
from builder.models import PromoCode, PromoRedemption, User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

logger = logging.getLogger("builder.store")

# Keys stored in platform_kv
KEY_PRICE = "subscription_price_stars"
KEY_DAYS = "subscription_days"
KEY_PAYMENTS = "payments_enabled"
KEY_PROMO_ON = "promo_enabled"
KEY_PROMO_DISC = "promo_discount_stars"
KEY_PROMO_TITLE = "promo_title"
KEY_PROMO_TEXT = "promo_text"


class Store:
    def __init__(self, settings: Settings, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.settings = settings
        self.sf = session_factory
        self._cache: dict[str, str] = {}

    async def get(self, key: str, default: str = "") -> str:
        if key in self._cache:
            return self._cache[key]
        from builder.models import PlatformKV

        async with self.sf() as s:
            row = await s.get(PlatformKV, key)
            if row:
                self._cache[key] = row.value
                return row.value
        return default

    async def set(self, key: str, value: str) -> None:
        from builder.models import PlatformKV

        async with self.sf() as s:
            row = await s.get(PlatformKV, key)
            if row:
                row.value = value
            else:
                s.add(PlatformKV(key=key, value=value))
            await s.commit()
        self._cache[key] = value
        logger.info("platform set %s=%s", key, value[:80])

    def clear_cache(self) -> None:
        self._cache.clear()
        clear_settings_cache()

    async def price_stars(self) -> int:
        raw = await self.get(KEY_PRICE, str(self.settings.subscription_price_stars))
        try:
            return max(50, int(raw))
        except ValueError:
            return self.settings.subscription_price_stars

    async def sub_days(self) -> int:
        raw = await self.get(KEY_DAYS, str(self.settings.subscription_days))
        try:
            return max(1, int(raw))
        except ValueError:
            return self.settings.subscription_days

    async def payments_on(self) -> bool:
        raw = await self.get(KEY_PAYMENTS, "1" if self.settings.payments_enabled else "0")
        return raw in {"1", "true", "True", "yes", "on"}

    async def promo_cfg(self) -> dict[str, Any]:
        on = await self.get(KEY_PROMO_ON, "1" if self.settings.promo_enabled else "0")
        disc = await self.get(KEY_PROMO_DISC, str(self.settings.promo_discount_stars))
        title = await self.get(KEY_PROMO_TITLE, self.settings.promo_title)
        text = await self.get(KEY_PROMO_TEXT, self.settings.promo_text)
        try:
            d = int(disc)
        except ValueError:
            d = self.settings.promo_discount_stars
        return {
            "enabled": on in {"1", "true", "True", "yes", "on"},
            "discount": max(0, d),
            "title": title,
            "text": text,
        }

    async def effective_base_price(self) -> int:
        price = await self.price_stars()
        promo = await self.promo_cfg()
        if promo["enabled"] and promo["discount"] > 0:
            price = max(50, price - promo["discount"])
        return price

    async def list_promos(self) -> list[PromoCode]:
        async with self.sf() as s:
            return list(
                (await s.execute(select(PromoCode).order_by(PromoCode.id.desc()).limit(50))).scalars().all()
            )

    async def create_promo(
        self,
        code: str,
        kind: str,
        value: int,
        max_uses: int = 100,
        note: str = "",
        days_valid: int = 30,
    ) -> PromoCode:
        code = code.strip().upper().replace(" ", "")
        async with self.sf() as s:
            exists = (
                await s.execute(select(PromoCode).where(PromoCode.code == code))
            ).scalar_one_or_none()
            if exists:
                raise ValueError("Bu kod allaqachon bor")
            p = PromoCode(
                code=code,
                kind=kind,
                value=max(0, value),
                max_uses=max(1, max_uses),
                used_count=0,
                active=True,
                note=note[:200],
                expires_at=utcnow() + timedelta(days=max(1, days_valid)),
            )
            s.add(p)
            await s.commit()
            await s.refresh(p)
            return p

    async def toggle_promo(self, promo_id: int) -> Optional[PromoCode]:
        async with self.sf() as s:
            p = await s.get(PromoCode, promo_id)
            if not p:
                return None
            p.active = not p.active
            await s.commit()
            await s.refresh(p)
            return p

    async def redeem_promo(self, telegram_id: int, code: str) -> str:
        """Apply promo to user. Returns human message."""
        code = code.strip().upper().replace(" ", "")
        async with self.sf() as s:
            u = (await s.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
            if not u:
                raise ValueError("Avval /start bosing")
            p = (await s.execute(select(PromoCode).where(PromoCode.code == code))).scalar_one_or_none()
            if not p or not p.active:
                raise ValueError("Kod noto‘g‘ri yoki o‘chiq")
            exp = as_utc(p.expires_at)
            if exp and exp < utcnow():
                raise ValueError("Kod muddati tugagan")
            if p.used_count >= p.max_uses:
                raise ValueError("Kod limiti tugagan")
            used = (
                await s.execute(
                    select(PromoRedemption).where(
                        PromoRedemption.promo_id == p.id, PromoRedemption.user_id == u.id
                    )
                )
            ).scalar_one_or_none()
            if used:
                raise ValueError("Bu kodni allaqachon ishlatgansiz")

            msg = ""
            if p.kind == "stars":
                u.credit_stars = int(u.credit_stars or 0) + int(p.value)
                msg = f"✅ +{p.value} Stars bonus hisobingizga qo‘shildi"
            elif p.kind == "percent":
                # convert percent of base price to credit
                base = await self.price_stars()
                credit = max(1, int(base * min(90, p.value) / 100))
                u.credit_stars = int(u.credit_stars or 0) + credit
                msg = f"✅ {p.value}% chegirma · +{credit}★ bonus"
            elif p.kind == "credit":
                u.credit_stars = int(u.credit_stars or 0) + int(p.value)
                msg = f"✅ +{p.value}★ kredit"
            elif p.kind == "days":
                from builder.models import Subscription

                sub = (
                    await s.execute(
                        select(Subscription)
                        .where(Subscription.user_id == u.id)
                        .order_by(Subscription.id.desc())
                    )
                ).scalars().first()
                if sub and sub.expires_at:
                    base = as_utc(sub.expires_at) or utcnow()
                    sub.expires_at = base + timedelta(days=int(p.value))
                    sub.status = "active"
                    msg = f"✅ Obunaga +{p.value} kun qo‘shildi"
                else:
                    now = utcnow()
                    ns = Subscription(
                        user_id=u.id,
                        status="active",
                        plan_code="promo_days",
                        price_stars=0,
                        starts_at=now,
                        expires_at=now + timedelta(days=int(p.value)),
                        grace_until=now + timedelta(days=int(p.value) + 7),
                        auto_renew=False,
                        expired_notice_sent=False,
                    )
                    s.add(ns)
                    msg = f"✅ {p.value} kunlik promo obuna faol"
            else:
                raise ValueError("Noma’lum promo turi")

            p.used_count += 1
            s.add(PromoRedemption(promo_id=p.id, user_id=u.id))
            await s.commit()
            return msg


def gen_code(prefix: str = "MF") -> str:
    return f"{prefix}{secrets.token_hex(3).upper()}"
