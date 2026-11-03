import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("SMA_SHARED_SECRET", None)
os.environ["RATE_LIMIT_PER_MINUTE"] = "1000"

from fastapi.testclient import TestClient  # noqa: E402
from app import app  # noqa: E402

client = TestClient(app)


def test_health_root_and_prefix():
    for path in ("/health", "/sma-extension/health"):
        response = client.get(path)
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert data["status"] == "online"
        assert data["authenticationAccepted"] is True


def test_chat_local_fallback():
    response = client.post(
        "/api/chat",
        json={
            "screen": "sales-report",
            "question": "Which companies need attention?",
            "scope": "all",
            "rows": [
                {"companyName": "Alpha", "totalBalance": 1000, "risks": ["ATT", "BT"]},
                {"companyName": "Beta", "totalBalance": 500, "risks": ["To Call"]},
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["mode"] == "local-fallback"
    assert data["report"]["companiesAnalyzed"] == 2
    assert "Alpha" in data["answer"]


def test_notes_analysis():
    response = client.post(
        "/sma/analyze-notes",
        json={
            "notesData": {
                "companyName": "Example Co",
                "notes": [{"date": "2026-08-01", "notice": "Client has low usage and needs a call."}],
            }
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["aiSummary"]["account_facts"]["company"] == "Example Co"


def test_prefix_chat_route():
    response = client.post(
        "/sma-extension/api/chat",
        json={"screen": "company-notes", "question": "Summarize", "notesData": {"notes": []}},
    )
    assert response.status_code == 200


def test_reject_missing_question():
    response = client.post("/api/chat", json={"rows": []})
    assert response.status_code == 400


def test_reject_non_json():
    response = client.post("/api/chat", content="hello", headers={"Content-Type": "text/plain"})
    assert response.status_code == 400


def test_priority_notification_requires_smtp():
    response = client.post(
        "/sma/notify-sales-priority",
        json={"veryUrgentCompanies": [{"companyName": "Alpha"}]},
    )
    assert response.status_code == 503
    assert response.json()["logged"] is True


def test_generic_allowlisted_routes():
    paths = [
        "/sma/analyze-company",
        "/sma/analyze-page",
        "/sma/analyze-category-monthly-delivery",
        "/sma/analyze-route",
    ]
    for path in paths:
        response = client.post(path, json={"screen": "test", "rows": [{"companyName": "Alpha"}]})
        assert response.status_code == 200, path
        assert response.json()["ok"] is True


def test_draft_followup_and_log_action():
    response = client.post("/sma/draft-followup", json={"companyName": "Alpha"})
    assert response.status_code == 200
    assert "Alpha" in response.json()["message"]

    response = client.post("/sma/log-action", json={"action": "opened", "companyName": "Alpha"})
    assert response.status_code == 200
    assert response.json()["logged"] is True


def test_openai_response_path_is_wired(monkeypatch):
    from app import openai_service

    monkeypatch.setattr(openai_service, "client", object())
    monkeypatch.setattr(openai_service, "answer", lambda payload: "Mock AI answer")
    response = client.post(
        "/api/chat",
        json={"screen": "sales-report", "question": "Analyze", "rows": [{"companyName": "Alpha"}]},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "openai"
    assert data["answer"] == "Mock AI answer"


def test_openai_notes_path_is_wired(monkeypatch):
    from app import openai_service

    monkeypatch.setattr(openai_service, "client", object())
    monkeypatch.setattr(
        openai_service,
        "notes_summary",
        lambda notes: {
            "executive_summary": "Mock summary",
            "latest_updates_summary": "Mock latest",
            "account_facts": {"company": "Alpha"},
            "risks": [],
            "next_best_action": "Call",
            "department_summary": {},
        },
    )
    response = client.post("/sma/analyze-notes", json={"notesData": {"notes": []}})
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "openai"
    assert data["summary"] == "Mock summary"
