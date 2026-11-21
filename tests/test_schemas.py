import pytest
from pydantic import ValidationError

from src.schemas import (
    Category,
    Priority,
    Ticket,
    TriageResult,
    ReviewRecord,
)


def test_category_and_priority_enums():
    assert Category.BILLING.value == "billing"
    assert Category.TECHNICAL_BUG.value == "technical_bug"
    assert Category.ACCOUNT_ACCESS.value == "account_access"
    assert Category.SECURITY_PRIVACY.value == "security_privacy"
    assert Category.FEATURE_REQUEST.value == "feature_request"
    assert Category.GENERAL_INQUIRY.value == "general_inquiry"

    assert Priority.URGENT.value == "urgent"
    assert Priority.HIGH.value == "high"
    assert Priority.MEDIUM.value == "medium"
    assert Priority.LOW.value == "low"

    with pytest.raises(ValueError):
        Category("invalid_category")

    with pytest.raises(ValueError):
        Priority("invalid_priority")


def test_ticket_model_validation():
    ticket = Ticket(
        id="TCK-100",
        subject="Payment failed",
        body="My card was declined when trying to upgrade.",
        created_at="2026-11-21T10:00:00Z",
        metadata={"user_tier": "enterprise"},
    )
    assert ticket.id == "TCK-100"
    assert ticket.subject == "Payment failed"
    assert ticket.metadata["user_tier"] == "enterprise"

    # Non-empty ID validation
    with pytest.raises(ValidationError):
        Ticket(id="", subject="Test", body="Valid body text here")

    with pytest.raises(ValidationError):
        Ticket(id="   ", subject="Test", body="Valid body text here")


def test_triage_result_bounds_and_reasoning():
    result = TriageResult(
        category=Category.BILLING,
        priority=Priority.HIGH,
        confidence=0.85,
        reasoning="Customer discusses billing issue.",
    )
    assert result.confidence == 0.85
    assert result.category == Category.BILLING

    # Confidence bounds [0.0, 1.0]
    with pytest.raises(ValidationError):
        TriageResult(
            category=Category.BILLING,
            priority=Priority.HIGH,
            confidence=-0.01,
            reasoning="Too low",
        )

    with pytest.raises(ValidationError):
        TriageResult(
            category=Category.BILLING,
            priority=Priority.HIGH,
            confidence=1.01,
            reasoning="Too high",
        )

    # Empty reasoning rejection
    with pytest.raises(ValidationError):
        TriageResult(
            category=Category.BILLING,
            priority=Priority.HIGH,
            confidence=0.9,
            reasoning="   ",
        )


def test_review_record_creation():
    rec = ReviewRecord(
        ticket_id="TCK-999",
        raw_data={"broken": True},
        escalation_reason="invalid_input",
    )
    assert rec.ticket_id == "TCK-999"
    assert rec.escalation_reason == "invalid_input"
