from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import settings


def _async_url(url: str) -> str:
    return url.replace("sqlite:///", "sqlite+aiosqlite:///")


engine: AsyncEngine = create_async_engine(_async_url(settings.database_url), echo=settings.debug)


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.execute(text("SELECT 1"))
