# repositories.py
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Tender, TenderStatus, TenderSummary


class TenderRepository:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(self, filename: str, storage_path: str) -> Tender:
        tender = Tender(
            filename=filename,
            storage_path=storage_path,
            status=TenderStatus.QUEUED,
        )
        self._db.add(tender)
        await self._db.commit()
        await self._db.refresh(tender)
        return tender

    async def get(self, tender_id: UUID) -> Tender | None:
        result = await self._db.execute(
            select(Tender).where(Tender.id == tender_id)
        )
        return result.scalar_one_or_none()

    async def get_with_summary(self, tender_id: UUID) -> Tender | None:
        stmt = (
            select(Tender)
            .where(Tender.id == tender_id)
            .options(selectinload(Tender.summary))
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[Tender]:
        stmt = (
            select(Tender)
            .order_by(Tender.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def set_status(
        self,
        tender_id: UUID,
        status: TenderStatus,
        error_message: str | None = None,
    ) -> None:
        tender = await self.get(tender_id)
        if tender is None:
            raise ValueError("Tender not found")
        tender.status = status
        tender.error_message = error_message
        await self._db.commit()

    async def save_summary(self, tender_id: UUID, summary_fields: dict) -> None:
        summary = TenderSummary(tender_id=tender_id, **summary_fields)
        self._db.add(summary)
        await self._db.commit()
        await self._db.refresh(summary)