"""Async engine and session factory.

One engine per process. The API gets a session per request via `get_session`;
Celery tasks open their own with `session_factory()`.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings, get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def build_engine(settings: Settings) -> AsyncEngine:
    kwargs: dict[str, object] = {"echo": settings.database_echo, "pool_pre_ping": True}
    if not settings.database_url.startswith("sqlite"):
        kwargs |= {"pool_size": settings.database_pool_size, "max_overflow": 5}
    return create_async_engine(settings.database_url, **kwargs)


def init_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine, _session_factory
    _engine = build_engine(settings or get_settings())
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> AsyncEngine:
    return _engine or init_engine()


def session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def dispose_engine() -> None:
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session (and transaction) per request.

    Commits if the handler returns normally, rolls back on any exception.
    """
    async with session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
