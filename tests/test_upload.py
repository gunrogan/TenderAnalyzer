# tests/test_upload.py
from uuid import uuid4

from models import TenderStatus


def test_upload_pdf_creates_tender(client, fake_repo, storage_dir, fake_task):
    resp = client.post(
        "/api/v1/files",
        files={
            "file": (
                "tender_doc.pdf",
                b"%PDF-1.4 fake content",
                "application/pdf",
            )
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["filename"] == "tender_doc.pdf"
    assert body["status"] == "queued"
    assert body["id"]
    assert fake_task.delay.called
    assert len(fake_repo.tenders) == 1

    tender = list(fake_repo.tenders.values())[0]
    assert tender.status == TenderStatus.QUEUED
    assert (storage_dir / tender.storage_path).exists()


def test_upload_rejects_non_pdf(client, fake_repo, storage_dir, fake_task):
    resp = client.post(
        "/api/v1/files",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert resp.status_code == 400
    assert "PDF" in resp.json()["detail"]
    assert fake_repo.tenders == {}
    assert not fake_task.delay.called


def test_upload_accepts_twice(client, fake_repo, storage_dir, fake_task):
    for i in range(2):
        resp = client.post(
            "/api/v1/files",
            files={
                "file": (
                    f"doc_{i}.pdf",
                    b"%PDF-1.4 fake",
                    "application/pdf",
                )
            },
        )
        assert resp.status_code == 201
    assert len(fake_repo.tenders) == 2