from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from platform_core.database import Base
from platform_core.enums import (
    DeploymentStatus,
    PaymentPurpose,
    PaymentStatus,
    SubscriptionStatus,
    TicketStatus,
    UserRole,
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[str] = mapped_column(String(8), default="uz")
    role: Mapped[str] = mapped_column(String(32), default=UserRole.USER.value)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")
    deployments: Mapped[list[Deployment]] = relationship(back_populates="user")
    payments: Mapped[list[Payment]] = relationship(back_populates="user")
    tickets: Mapped[list[Ticket]] = relationship(back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_status_expires", "status", "expires_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default=SubscriptionStatus.PENDING.value, index=True)
    plan_code: Mapped[str] = mapped_column(String(64), default="monthly_stars")
    price_stars: Mapped[int] = mapped_column(Integer, default=300)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_7d_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_3d_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    expired_notice_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    last_daily_reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="subscriptions")
    payments: Mapped[list[Payment]] = relationship(back_populates="subscription")
    deployment: Mapped[Optional[Deployment]] = relationship(back_populates="subscription", uselist=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (Index("ix_payments_telegram_payment_charge", "telegram_payment_charge_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    purpose: Mapped[str] = mapped_column(String(32), default=PaymentPurpose.NEW_SUBSCRIPTION.value)
    status: Mapped[str] = mapped_column(String(32), default=PaymentStatus.PENDING.value, index=True)
    amount_stars: Mapped[int] = mapped_column(Integer, default=300)
    currency: Mapped[str] = mapped_column(String(16), default="XTR")
    telegram_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[str] = mapped_column(String(255), default="")
    raw_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="payments")
    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="payments")


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_deployments_slug"),
        Index("ix_deployments_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    slug: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default=DeploymentStatus.PENDING.value)

    bot_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bot_first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    project_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    container_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    container_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    process_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    db_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    database_url_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    redis_namespace: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provisioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="deployments")
    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="deployment")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    deployment_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(128))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_telegram_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    is_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subject: Mapped[str] = mapped_column(String(255))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default=TicketStatus.OPEN.value)
    admin_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="tickets")


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default=UserRole.ADMIN.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
