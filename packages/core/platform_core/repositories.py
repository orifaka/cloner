from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from platform_core.enums import DeploymentStatus, PaymentStatus, SubscriptionStatus
from platform_core.models import (
    ActivityLog,
    AuditLog,
    Deployment,
    Notification,
    Payment,
    Subscription,
    Ticket,
    User,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        username: Optional[str],
        full_name: str,
        language: str = "uz",
        is_admin: bool = False,
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.username = username
            user.full_name = full_name or user.full_name
            if is_admin:
                user.role = "admin"
            await self.session.commit()
            await self.session.refresh(user)
            return user
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            language=language,
            role="admin" if is_admin else "user",
        )
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def list_all(self, limit: int = 200) -> Sequence[User]:
        result = await self.session.execute(select(User).order_by(User.id.desc()).limit(limit))
        return result.scalars().all()


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, price_stars: int) -> Subscription:
        sub = Subscription(
            user_id=user_id,
            status=SubscriptionStatus.PENDING.value,
            price_stars=price_stars,
        )
        self.session.add(sub)
        await self.session.commit()
        await self.session.refresh(sub)
        return sub

    async def get(self, subscription_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.deployment), selectinload(Subscription.user))
            .where(Subscription.id == subscription_id)
        )
        return result.scalar_one_or_none()

    async def get_active_for_user(self, user_id: int) -> Optional[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.deployment))
            .where(
                Subscription.user_id == user_id,
                Subscription.status.in_(
                    [
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.GRACE.value,
                        SubscriptionStatus.PENDING.value,
                    ]
                ),
            )
            .order_by(Subscription.id.desc())
        )
        return result.scalars().first()

    async def list_for_lifecycle(self) -> Sequence[Subscription]:
        result = await self.session.execute(
            select(Subscription)
            .options(selectinload(Subscription.user), selectinload(Subscription.deployment))
            .where(
                Subscription.status.in_(
                    [
                        SubscriptionStatus.ACTIVE.value,
                        SubscriptionStatus.GRACE.value,
                        SubscriptionStatus.EXPIRED.value,
                    ]
                )
            )
        )
        return result.scalars().all()

    async def save(self, sub: Subscription) -> Subscription:
        await self.session.commit()
        await self.session.refresh(sub)
        return sub


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        subscription_id: int,
        amount_stars: int,
        purpose: str,
        payload: str,
    ) -> Payment:
        payment = Payment(
            user_id=user_id,
            subscription_id=subscription_id,
            amount_stars=amount_stars,
            purpose=purpose,
            payload=payload,
            status=PaymentStatus.PENDING.value,
        )
        self.session.add(payment)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def get_by_payload(self, payload: str) -> Optional[Payment]:
        result = await self.session.execute(select(Payment).where(Payment.payload == payload))
        return result.scalar_one_or_none()

    async def mark_success(
        self,
        payment: Payment,
        telegram_payment_charge_id: Optional[str],
        provider_payment_charge_id: Optional[str],
        raw_json: Optional[str] = None,
    ) -> Payment:
        payment.status = PaymentStatus.SUCCESS.value
        payment.telegram_payment_charge_id = telegram_payment_charge_id
        payment.provider_payment_charge_id = provider_payment_charge_id
        payment.raw_json = raw_json
        payment.paid_at = _utcnow()
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def list_recent(self, limit: int = 100) -> Sequence[Payment]:
        result = await self.session.execute(select(Payment).order_by(Payment.id.desc()).limit(limit))
        return result.scalars().all()

    async def total_stars_income(self) -> int:
        result = await self.session.execute(
            select(Payment).where(Payment.status == PaymentStatus.SUCCESS.value)
        )
        return sum(p.amount_stars for p in result.scalars().all())


class DeploymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        user_id: int,
        subscription_id: int,
        slug: str,
    ) -> Deployment:
        # Free unique subscription_id from soft-deleted rows
        old = (
            await self.session.execute(
                select(Deployment).where(
                    Deployment.subscription_id == subscription_id,
                    Deployment.status == DeploymentStatus.DELETED.value,
                )
            )
        ).scalars().all()
        for row in old:
            row.subscription_id = None
        dep = Deployment(
            user_id=user_id,
            subscription_id=subscription_id,
            slug=slug,
            status=DeploymentStatus.PENDING.value,
        )
        self.session.add(dep)
        await self.session.commit()
        await self.session.refresh(dep)
        return dep

    async def get(self, deployment_id: int) -> Optional[Deployment]:
        result = await self.session.execute(
            select(Deployment)
            .options(selectinload(Deployment.user), selectinload(Deployment.subscription))
            .where(Deployment.id == deployment_id)
        )
        return result.scalar_one_or_none()

    async def get_by_user(self, user_id: int) -> Optional[Deployment]:
        result = await self.session.execute(
            select(Deployment)
            .options(selectinload(Deployment.subscription))
            .where(
                Deployment.user_id == user_id,
                Deployment.status != DeploymentStatus.DELETED.value,
            )
            .order_by(Deployment.id.desc())
        )
        return result.scalars().first()

    async def list_all(self, limit: int = 500) -> Sequence[Deployment]:
        result = await self.session.execute(
            select(Deployment).order_by(Deployment.id.desc()).limit(limit)
        )
        return result.scalars().all()

    async def list_by_status(self, status: str) -> Sequence[Deployment]:
        result = await self.session.execute(select(Deployment).where(Deployment.status == status))
        return result.scalars().all()

    async def save(self, dep: Deployment) -> Deployment:
        await self.session.commit()
        await self.session.refresh(dep)
        return dep


class LogRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def activity(
        self,
        action: str,
        user_id: Optional[int] = None,
        deployment_id: Optional[int] = None,
        detail: Optional[str] = None,
    ) -> None:
        self.session.add(
            ActivityLog(user_id=user_id, deployment_id=deployment_id, action=action, detail=detail)
        )
        await self.session.commit()

    async def audit(
        self,
        action: str,
        actor_telegram_id: Optional[int] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        detail: Optional[str] = None,
    ) -> None:
        self.session.add(
            AuditLog(
                actor_telegram_id=actor_telegram_id,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail,
            )
        )
        await self.session.commit()


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, ntype: str, title: str, body: str) -> Notification:
        note = Notification(user_id=user_id, type=ntype, title=title, body=body)
        self.session.add(note)
        await self.session.commit()
        await self.session.refresh(note)
        return note


class TicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: int, subject: str, body: str) -> Ticket:
        ticket = Ticket(user_id=user_id, subject=subject, body=body)
        self.session.add(ticket)
        await self.session.commit()
        await self.session.refresh(ticket)
        return ticket

    async def list_open(self) -> Sequence[Ticket]:
        result = await self.session.execute(
            select(Ticket).where(Ticket.status != "closed").order_by(Ticket.id.desc())
        )
        return result.scalars().all()
