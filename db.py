from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from config import settings


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def worker_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Сессия для Celery threads-вориер.
    Пул соединлений привязывает asyncpg-соединение к event loop своего
    потока.
    """
    worker_engine = create_async_engine(
        settings.database_url, poolclass=NullPool
    )
    worker_factory = async_sessionmaker(
        worker_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    try:
        async with worker_factory() as session:
            yield session
    finally:
        await worker_engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-зависимость, выдающая сессию БД на время обработки запроса."""
    async with async_session_factory() as session:
        yield session