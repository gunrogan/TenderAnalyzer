# tasks.py
from __future__ import annotations

import asyncio
from uuid import UUID

from celery import Celery

from config import settings
from db import async_session_factory, dispose_engine
from events import publish_status
from llm import extract_text, summarize_document
from models import TenderStatus
from repositories import TenderRepository

celery_app = Celery(
    "tenderdigest",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    timezone="UTC",
    enable_utc=True,
    # Таймаут только на установку соединения. НЕ задаём socket_timeout
    # (timeout на чтение): он рвёт соединение посреди чтения сообщения и
    # вызывает ошибки «not enough values to unpack» в воркере.
    broker_connection_timeout=5,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "socket_connect_timeout": 5,
    },
    # threads-пул вместо prefork: на Windows prefork (spawn) вызывает
    # "not enough values to unpack" в fast_trace_task.
    worker_pool=settings.worker_pool,
    worker_concurrency=settings.worker_concurrency,
)


@celery_app.task(name="analyze_tender_file")
def analyze_tender_file(tender_id: str) -> None:
    """Celery-задача фоновой обработки PDF и генерации выжимки."""
    # threads-пул: каждое выполнение задачи может идти в новом потоке.
    # Создаём ОДИН event loop на задачу и закрываем его после — так
    # asyncpg-соединения, созданные внутри, не попадут в "Event loop is closed".
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_process(UUID(tender_id)))
    finally:
        # Закрыть asyncpg-соединения в этом же loop, чтобы не осталось
        # "Event loop is closed" в следующей задаче/потоке.
        try:
            loop.run_until_complete(dispose_engine())
        except Exception:
            pass
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


async def _process(tender_id: UUID) -> None:
    async with async_session_factory() as db:
        repo = TenderRepository(db)
        tender = await repo.get(tender_id)
        if tender is None:
            return
        await repo.set_status(tender_id, TenderStatus.PROCESSING)
    await publish_status(tender_id, TenderStatus.PROCESSING.value)

    try:
        text = await extract_text(tender.storage_path)
        summary = await summarize_document(text)
        async with async_session_factory() as db:
            repo = TenderRepository(db)
            await repo.save_summary(tender_id, summary)
            await repo.set_status(tender_id, TenderStatus.COMPLETED)
        await publish_status(tender_id, TenderStatus.COMPLETED.value)
    except Exception as exc:
        async with async_session_factory() as db:
            repo = TenderRepository(db)
            await repo.set_status(
                tender_id, TenderStatus.FAILED, error_message=str(exc)
            )
        await publish_status(tender_id, TenderStatus.FAILED.value, str(exc))