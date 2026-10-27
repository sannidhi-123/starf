"""Async SQLAlchemy engine, declarative base and session factory.

All ORM models must inherit from ``Base``.  Tables are created inside
``init_db()`` which is called once at application startup via the lifespan hook.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


def _async_url(url: str) -> str:
    return url.replace("sqlite:///", "sqlite+aiosqlite:///")


engine: AsyncEngine = create_async_engine(
    _async_url(settings.database_url), echo=settings.debug
)

SessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Shared SQLAlchemy 2.0 declarative base for all ORM models."""


async def init_db() -> None:
    """Verify DB connectivity and create all ORM-registered tables."""
    # Import models so SQLAlchemy registers them with Base.metadata
    import app.modules.alerts.models  # noqa: F401

    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))
        await connection.run_sync(Base.metadata.create_all)
        # create_all does not add columns to an existing SQLite database.
        if connection.dialect.name == "sqlite":
            columns = await connection.exec_driver_sql("PRAGMA table_info(alerts)")
            if "details" not in {row[1] for row in columns.fetchall()}:
                await connection.exec_driver_sql(
                    "ALTER TABLE alerts ADD COLUMN details JSON NOT NULL DEFAULT '{}'"
                )


async def close_db() -> None:
    """Dispose of the database engine and close all pooled connections."""
    global engine
    if engine is not None:
        await engine.dispose()
