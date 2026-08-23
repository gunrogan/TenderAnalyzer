from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db import get_session
from events import status_event_stream
from models import Tender, TenderStatus
from repositories import TenderRepository
from schemas import (
    FileListResponse,
    TenderDetailResponse,
    TenderFileResponse,
)
from storage import save_upload
from tasks import analyze_tender_file

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage_dir).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(
    title="TenderDigest",
    description="Анализ тендерной документации (PDF) с помощью LLM.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_repo(db: AsyncSession = Depends(get_session)) -> TenderRepository:
    return TenderRepository(db)


def _file_value(tender: Tender) -> str:
    return (
        tender.status.value
        if isinstance(tender.status, TenderStatus)
        else tender.status
    )


def _tender_file_response(tender: Tender) -> TenderFileResponse:
    return TenderFileResponse(
        id=tender.id,
        filename=tender.filename,
        status=_file_value(tender),
        error_message=tender.error_message,
        created_at=tender.created_at,
        updated_at=tender.updated_at,
    )


def _detail_response(tender: Tender) -> TenderDetailResponse:
    item = _tender_file_response(tender)
    summary = None
    if tender.summary is not None:
        s = tender.summary
        summary = {
            "tender_id": s.tender_id,
            "contract_amount": s.contract_amount,
            "execution_period": s.execution_period,
            "requirements": s.requirements,
            "penalties": s.penalties,
            "raw_llm_response": s.raw_llm_response,
        }
    return TenderDetailResponse(**item.model_dump(), summary=summary)


@app.post(
    "/api/v1/files",
    response_model=TenderFileResponse,
    status_code=201,
    summary="Загрузить PDF для анализа",
)
async def upload_file(
    file: UploadFile = File(..., description="PDF-файл тендерной документации"),
    repo: TenderRepository = Depends(get_repo),
):
    """Принимает PDF, сохраняет в хранилище, ставит в очередь на обработку."""
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Разрешены только PDF-файлы"
        )

    tender_id = uuid.uuid4()
    try:
        storage_path = await save_upload(file, str(tender_id))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    tender = await repo.create(filename, storage_path)
    try:
        analyze_tender_file.delay(str(tender.id))
    except Exception:
        logger.exception("Не удалось поставить задачу в очередь")
    return _tender_file_response(tender)


@app.get(
    "/api/v1/files",
    response_model=FileListResponse,
    summary="Список файлов со статусами",
)
async def list_files(
    limit: int = 100,
    offset: int = 0,
    repo: TenderRepository = Depends(get_repo),
):
    tenders = await repo.list(limit=max(1, min(limit, 1000)), offset=max(0, offset))
    return FileListResponse(items=[_tender_file_response(t) for t in tenders])


@app.get(
    "/api/v1/files/{tender_id}",
    response_model=TenderDetailResponse,
    summary="Получить файл и, при готовности, его выжимку",
)
async def get_file(
    tender_id: UUID,
    repo: TenderRepository = Depends(get_repo),
):
    """Возвращает суммаризацию, если обработка завершена, иначе ошибку со статусом."""
    tender = await repo.get_with_summary(tender_id)
    if tender is None:
        raise HTTPException(status_code=404, detail="Файл не найден")

    if tender.status == TenderStatus.COMPLETED:
        return _detail_response(tender)

    status_value = _file_value(tender)
    if tender.status == TenderStatus.FAILED:
        error = tender.error_message or "Не удалось обработать файл"
    else:
        error = "Файл ещё в обработке, выжимка пока недоступна"
    raise HTTPException(
        status_code=409,
        detail=error,
        headers={"X-Tender-Status": status_value},
    )


@app.get(
    "/api/v1/events",
    summary="SSE-поток смены статусов файлов",
)
async def events():
    return StreamingResponse(
        status_event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )