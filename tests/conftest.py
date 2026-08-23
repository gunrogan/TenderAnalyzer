# tests/conftest.py
from datetime import UTC, datetime
from unittest import mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from main import app, get_repo
from models import Tender, TenderStatus, TenderSummary


class FakeRepo:
    """In-memory реализация TenderRepository для тестов."""

    def __init__(self):
        self.tenders = {}

    def seed(
        self,
        *,
        filename="doc.pdf",
        storage="1.pdf",
        status=TenderStatus.QUEUED,
        error_message=None,
        summary=None,
    ):
        tender = Tender(
            id=uuid4(),
            filename=filename,
            storage_path=storage,
            status=status,
            error_message=error_message,
        )
        tender.created_at = datetime.now(UTC)
        tender.updated_at = datetime.now(UTC)
        if summary is not None:
            tender.summary = summary
        self.tenders[str(tender.id)] = tender
        return tender

    async def create(self, filename, storage_path):
        tender = Tender(
            filename=filename,
            storage_path=storage_path,
            status=TenderStatus.QUEUED,
        )
        tender.id = uuid4()
        tender.created_at = datetime.now(UTC)
        tender.updated_at = datetime.now(UTC)
        self.tenders[str(tender.id)] = tender
        return tender

    async def get(self, tender_id):
        return self.tenders.get(str(tender_id))

    async def get_with_summary(self, tender_id):
        return self.tenders.get(str(tender_id))

    async def list(self, limit=100, offset=0):
        items = list(self.tenders.values())
        return items[offset : offset + limit]

    async def set_status(self, tender_id, status, error_message=None):
        tender = self.tenders.get(str(tender_id))
        if tender is not None:
            tender.status = status
            tender.error_message = error_message

    async def save_summary(self, tender_id, summary_fields):
        tender = self.tenders.get(str(tender_id))
        if tender is not None:
            tender.summary = TenderSummary(tender_id=tender.id, **summary_fields)


@pytest.fixture
def fake_repo():
    return FakeRepo()


@pytest.fixture
def client(fake_repo):
    def _override():
        return fake_repo

    app.dependency_overrides[get_repo] = _override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def storage_dir(tmp_path, monkeypatch):
    import main

    monkeypatch.setattr(main.settings, "storage_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def fake_task(monkeypatch):
    import main

    task = mock.Mock()
    monkeypatch.setattr(main, "analyze_tender_file", task)
    return task