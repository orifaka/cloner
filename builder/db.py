from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from builder.config import Settings, get_settings

logger = logging.getLogger("builder.db")


class Base(DeclarativeBase):
    pass


_engine: Optional[AsyncEngine] = None
_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine(settings: Optional[Settings] = None) -> AsyncEngine:
    global _engine
    if _engine is None:
        cfg = settings or get_settings()
        kwargs: dict = {"echo": False, "pool_pre_ping": True}
        if cfg.platform_database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(cfg.platform_database_url, **kwargs)
    return _engine


def get_session_factory(settings: Optional[Settings] = None) -> async_sessionmaker[AsyncSession]:
    global _factory
    if _factory is None:
        _factory = async_sessionmaker(get_engine(settings), expire_on_commit=False, class_=AsyncSession)
    return _factory


async def _sqlite_add_column(conn, table: str, column: str, coltype: str) -> None:
    try:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
        logger.info("migrated %s.%s", table, column)
    except Exception:  # noqa: BLE001
        pass  # already exists


async def migrate_schema(settings: Optional[Settings] = None) -> None:
    """Add new columns on existing SQLite DBs without wiping data."""
    eng = get_engine(settings)
    async with eng.begin() as conn:
        # users
        await _sqlite_add_column(conn, "users", "referral_code", "VARCHAR(32)")
        await _sqlite_add_column(conn, "users", "referred_by_id", "INTEGER")
        await _sqlite_add_column(conn, "users", "credit_stars", "INTEGER DEFAULT 0")
        await _sqlite_add_column(conn, "users", "referral_paid", "BOOLEAN DEFAULT 0")
        await _sqlite_add_column(conn, "users", "updated_at", "DATETIME")
        # subscriptions (legacy columns from older schema)
        await _sqlite_add_column(conn, "subscriptions", "plan_code", "VARCHAR(64) DEFAULT 'monthly_stars'")
        await _sqlite_add_column(conn, "subscriptions", "auto_renew", "BOOLEAN DEFAULT 0")
        await _sqlite_add_column(conn, "subscriptions", "expired_notice_sent", "BOOLEAN DEFAULT 0")
        await _sqlite_add_column(conn, "subscriptions", "updated_at", "DATETIME")
        # backfill NULL plan_code so NOT NULL inserts never fail
        try:
            await conn.execute(
                text("UPDATE subscriptions SET plan_code='monthly_stars' WHERE plan_code IS NULL OR plan_code=''")
            )
        except Exception:  # noqa: BLE001
            pass
        # deployments legacy
        await _sqlite_add_column(conn, "deployments", "container_id", "VARCHAR(128)")
        await _sqlite_add_column(conn, "deployments", "container_name", "VARCHAR(128)")
        await _sqlite_add_column(conn, "deployments", "redis_namespace", "VARCHAR(64)")
        await _sqlite_add_column(conn, "deployments", "updated_at", "DATETIME")
        # payments
        await _sqlite_add_column(conn, "payments", "raw_json", "TEXT")


async def init_db(settings: Optional[Settings] = None) -> None:
    eng = get_engine(settings)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await migrate_schema(settings)


async def close_db() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
