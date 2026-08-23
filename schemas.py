# schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenderFileResponse(BaseModel):
    """Короткое представление загруженного файла (без суммаризаций)."""

    id: UUID
    filename: str
    status: str
    error_message: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class FileListResponse(BaseModel):
    items: list[TenderFileResponse]


class TenderSummaryResponse(BaseModel):
    tender_id: UUID
    contract_amount: Optional[str] = None
    execution_period: Optional[str] = None
    requirements: Optional[list] = None
    penalties: Optional[list] = None
    raw_llm_response: Optional[dict] = None

    model_config = ConfigDict(from_attributes=True)


class TenderDetailResponse(TenderFileResponse):
    summary: Optional[TenderSummaryResponse] = None