# tests/test_files.py
from uuid import uuid4

from models import TenderStatus, TenderSummary


def test_list_files_returns_items(client, fake_repo):
    fake_repo.seed(filename="a.pdf")
    fake_repo.seed(filename="b.pdf")
    resp = client.get("/api/v1/files")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert {item["status"] for item in body["items"]} == {"queued"}


def test_list_files_respects_pagination(client, fake_repo):
    for i in range(5):
        fake_repo.seed(filename=f"f_{i}.pdf")
    resp = client.get("/api/v1/files", params={"limit": 2, "offset": 0})
    assert len(resp.json()["items"]) == 2


def test_get_completed_returns_summary(client, fake_repo):
    tender = fake_repo.seed(status=TenderStatus.COMPLETED)
    tender.summary = TenderSummary(
        tender_id=tender.id,
        contract_amount="1 000 000 руб.",
        execution_period="до 30.06.2026",
        requirements=["Лицензия", "СРО"],
        penalties=["Неустойка 0,5%/день"],
    )
    resp = client.get(f"/api/v1/files/{tender.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    summary = body["summary"]
    assert summary["contract_amount"] == "1 000 000 руб."
    assert summary["execution_period"] == "до 30.06.2026"
    assert summary["requirements"] == ["Лицензия", "СРО"]
    assert summary["penalties"] == ["Неустойка 0,5%/день"]


def test_get_failed_returns_error(client, fake_repo):
    tender = fake_repo.seed(
        status=TenderStatus.FAILED, error_message="PDF повреждён"
    )
    resp = client.get(f"/api/v1/files/{tender.id}")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "PDF повреждён"
    assert resp.headers.get("x-tender-status") == "failed"


def test_get_in_progress_returns_conflict(client, fake_repo):
    tender = fake_repo.seed(status=TenderStatus.PROCESSING)
    resp = client.get(f"/api/v1/files/{tender.id}")
    assert resp.status_code == 409
    assert resp.headers.get("x-tender-status") == "processing"
    assert "в обработке" in resp.json()["detail"]


def test_get_missing_returns_404(client, fake_repo):
    resp = client.get(f"/api/v1/files/{uuid4()}")
    assert resp.status_code == 404