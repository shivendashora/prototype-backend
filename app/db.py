"""Async SQLAlchemy (2.x) + asyncpg setup for user-submitted data.

Seed/catalogue data (providers, courses) lives in JSON files under app/data.
ORM models live in app/models.py; tables are created on startup via
`Base.metadata.create_all`.
"""
import logging
import os
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

log = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _database_url() -> URL:
    """Connection string comes only from the environment (backend/.env).

    Accepts plain `postgresql://` / `postgres://` URLs (as hosting providers give them)
    and switches them to the asyncpg driver. `sslmode=` is mapped to asyncpg's `ssl=`.
    """
    raw = os.getenv("DATABASE_URL")
    if not raw:
        raise RuntimeError("DATABASE_URL is not set. Add it to backend/.env (see .env.example).")
    url = make_url(raw.replace("postgres://", "postgresql://", 1))
    if url.drivername in ("postgresql", "postgresql+psycopg2", "postgresql+psycopg"):
        url = url.set(drivername="postgresql+asyncpg")
    if "sslmode" in url.query:
        query = dict(url.query)
        query["ssl"] = query.pop("sslmode")
        url = url.set(query=query)
    return url


async def _ensure_database(url: URL) -> None:
    """Create the target database if it doesn't exist (local dev convenience).

    Silently skipped when the user can't reach the `postgres` maintenance DB,
    which is normal on managed hosts where the database already exists.
    """
    admin = create_async_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            exists = await conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database})
            if not exists:
                await conn.execute(text(f'CREATE DATABASE "{url.database}"'))
                log.info("Created database %s", url.database)
    except Exception as e:  # noqa: BLE001
        log.debug("Skipping database auto-create: %s", e)
    finally:
        await admin.dispose()


async def connect() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        return
    url = _database_url()
    await _ensure_database(url)
    _engine = create_async_engine(
        url,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    from . import models  # noqa: F401  (register models on Base.metadata)

    async with engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
        _engine = _sessionmaker = None


def engine() -> AsyncEngine:
    if _engine is None:
        raise RuntimeError("Database not initialised; call db.connect() first")
    return _engine


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one AsyncSession per request."""
    if _sessionmaker is None:
        raise RuntimeError("Database not initialised; call db.connect() first")
    async with _sessionmaker() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def ping() -> bool:
    try:
        async with engine().connect() as conn:
            return await conn.scalar(text("SELECT 1")) == 1
    except Exception:  # noqa: BLE001 - health check must never raise
        return False
