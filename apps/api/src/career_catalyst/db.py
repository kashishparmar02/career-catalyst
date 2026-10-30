"""Database engine and session factory shared by the whole API.

The engine is created lazily on first use, so importing the app (for tests or tooling)
never opens a connection.
"""

from collections.abc import AsyncIterator
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from career_catalyst.config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    return create_async_engine(str(get_settings().database_url), pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed when the request ends."""
    async with get_sessionmaker()() as session:
        yield session


async def ping_database() -> bool:
    """Return True if the database answers a trivial query; never raises."""
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        return False
    return True
