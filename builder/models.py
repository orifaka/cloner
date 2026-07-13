from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from builder.db import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    language: Mapped[str] = mapped_column(String(8), default="uz")
    role: Mapped[str] = mapped_column(String(32), default="user")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="user")
    deployments: Mapped[list[Deployment]] = relationship(back_populates="user")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    price_stars: Mapped[int] = mapped_column(Integer, default=300)
    starts_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    grace_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reminder_7d_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_3d_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    last_daily_reminder_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="subscriptions")
    deployment: Mapped[Optional[Deployment]] = relationship(back_populates="subscription", uselist=False)
    payments: Mapped[list[Payment]] = relationship(back_populates="subscription")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    purpose: Mapped[str] = mapped_column(String(32), default="new_subscription")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    amount_stars: Mapped[int] = mapped_column(Integer, default=300)
    currency: Mapped[str] = mapped_column(String(16), default="XTR")
    telegram_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    provider_payment_charge_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    payload: Mapped[str] = mapped_column(String(255), default="")
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="payments")


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (UniqueConstraint("slug", name="uq_deployments_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    subscription_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    slug: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")

    bot_token_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bot_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    bot_username: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    bot_first_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    project_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    process_pid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    db_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    database_url_encrypted: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    last_heartbeat_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    provisioned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped[User] = relationship(back_populates="deployments")
    subscription: Mapped[Optional[Subscription]] = relationship(back_populates="deployment")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deployment_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(128))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
