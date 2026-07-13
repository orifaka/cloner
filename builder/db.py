from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from builder.config import Settings, get_settings


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


async def init_db(settings: Optional[Settings] = None) -> None:
    eng = get_engine(settings)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    global _engine, _factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _factory = None
