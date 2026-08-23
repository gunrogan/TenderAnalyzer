# tasks.py
from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from celery import Celery

from config import settings
from db import worker_session_scope
from events import publish_status
from llm import extract_text, summarize_document
from models import TenderStatus
from repositories import TenderRepository

logger = logging.getLogger(__name__)

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
        # Закрыть async-генераторы и event loop. Соединения БД в воркере
        # управляются самим worker_session_scope (свой NullPool на вызов).
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


async def _process(tender_id: UUID) -> None:
    try:
        async with worker_session_scope() as db:
            repo = TenderRepository(db)
            tender = await repo.get(tender_id)
            if tender is None:
                return
            await repo.set_status(tender_id, TenderStatus.PROCESSING)
        await publish_status(tender_id, TenderStatus.PROCESSING.value)

        text = await extract_text(tender.storage_path)
        summary = await summarize_document(text)
        async with worker_session_scope() as db:
            repo = TenderRepository(db)
            await repo.save_summary(tender_id, summary)
            await repo.set_status(tender_id, TenderStatus.COMPLETED)
        await publish_status(tender_id, TenderStatus.COMPLETED.value)
    except Exception as exc:
        message = str(exc).strip() or f"{type(exc).__name__}: {exc!r}"
        logger.error(
            "Обработка файла %s завершилась ошибкой: %s",
            tender_id,
            message,
            exc_info=True,
        )
        async with worker_session_scope() as db:
            repo = TenderRepository(db)
            await repo.set_status(
                tender_id, TenderStatus.FAILED, error_message=message
            )
        await publish_status(tender_id, TenderStatus.FAILED.value, message)
        # Поднимаем исключение, чтобы Celery зафиксировал задачу как failed
        raise