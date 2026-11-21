import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api import app, TRIAGED_PATH, REVIEW_PATH, REPORT_PATH

client = TestClient(app)


def test_api_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "model" in data


def test_api_overview():
    res = client.get("/api/overview")
    assert res.status_code == 200
    data = res.json()
    assert "total" in data
    assert "autoCount" in data
    assert "humanReviewCount" in data
    assert "categoryData" in data
    assert "priorities" in data
    assert "escalationReasons" in data


def test_api_get_triaged_and_review_tickets():
    res_triaged = client.get("/api/tickets/triaged?limit=10")
    assert res_triaged.status_code == 200
    triaged_data = res_triaged.json()
    assert "tickets" in triaged_data
    assert "total" in triaged_data

    res_review = client.get("/api/tickets/review?limit=10")
    assert res_review.status_code == 200
    review_data = res_review.json()
    assert "tickets" in review_data
    assert "total" in review_data


def test_api_single_ticket_triage():
    # 1. Normal ticket
    res = client.post(
        "/api/triage/single",
        json={
            "id": "LIVE-TEST-1",
            "subject": "Need invoice for payment",
            "body": "Can you please email me the official receipt for last month billing?",
            "offline": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ticket_id"] == "LIVE-TEST-1"
    assert data["triaged"] is True
    assert data["triage"]["category"] == "billing"

    # 2. Insufficient context ticket (< 15 chars)
    res_short = client.post(
        "/api/triage/single",
        json={"subject": "Help", "body": "Need help", "offline": True},
    )
    assert res_short.status_code == 200
    data_short = res_short.json()
    assert data_short["triaged"] is False
    assert data_short["escalation_reason"] == "insufficient_context"


def test_api_approve_and_flag_lifecycle():
    # First get or ensure a review ticket exists
    review_res = client.get("/api/tickets/review")
    reviews = review_res.json()["tickets"]
    if reviews:
        target_ticket = reviews[0]
        ticket_id = target_ticket["id"]

        # Approve it
        appr_res = client.post(
            f"/api/tickets/{ticket_id}/approve",
            json={"category": "billing", "priority": "high", "notes": "Approved in test"},
        )
        assert appr_res.status_code == 200
        assert appr_res.json()["success"] is True

        # Now flag it back to review
        flag_res = client.post(f"/api/tickets/{ticket_id}/flag")
        assert flag_res.status_code == 200
        assert flag_res.json()["success"] is True


def test_api_settings_get_and_post():
    res = client.get("/api/settings")
    assert res.status_code == 200
    assert "threshold" in res.json()

    update_res = client.post("/api/settings", json={"threshold": 0.85})
    assert update_res.status_code == 200
    assert update_res.json()["settings"]["threshold"] == 0.85
