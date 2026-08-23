# tasks.py
from __future__ import annotations

import asyncio
from uuid import UUID

from celery import Celery

from config import settings
from db import async_session_factory
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
)


@celery_app.task(name="analyze_tender_file")
def analyze_tender_file(tender_id: str) -> None:
    """Celery-задача фоновой обработки PDF и генерации выжимки."""
    asyncio.run(_process(UUID(tender_id)))


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