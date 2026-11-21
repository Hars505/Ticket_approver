import pytest
from src.schemas import Category, Priority, Ticket, TriageResult
from src.guardrails import (
    normalize_text,
    has_urgent_keyword,
    evaluate_guardrails,
    RISK_KEYWORDS,
)


def test_normalize_text():
    raw = "  Server is DOWN! <br> Immediate   help needed.  "
    norm = normalize_text(raw)
    assert norm == "server is down! immediate help needed."


def test_has_urgent_keyword():
    assert has_urgent_keyword("Our production cluster crashed")
    assert has_urgent_keyword("System is down right now")
    assert has_urgent_keyword("Suspected security breach detected")
    assert has_urgent_keyword("I can't login to my account")
    assert has_urgent_keyword("Customer filed a chargeback")
    assert has_urgent_keyword("Potential data loss in table")
    assert not has_urgent_keyword("Please add dark mode toggle")
    assert not has_urgent_keyword("How do I update my profile?")


def test_evaluate_guardrails_insufficient_context():
    ticket = Ticket(
        id="TCK-1",
        subject="Help",
        body="Short text",  # 10 chars < 15
    )
    result = TriageResult(
        category=Category.GENERAL_INQUIRY,
        priority=Priority.LOW,
        confidence=0.95,
        reasoning="Simple question",
    )
    assert evaluate_guardrails(ticket, result) == "insufficient_context"


def test_evaluate_guardrails_low_confidence():
    ticket = Ticket(
        id="TCK-2",
        subject="Something weird happened",
        body="The buttons on the screen are behaving strangely sometimes.",
    )
    result = TriageResult(
        category=Category.TECHNICAL_BUG,
        priority=Priority.MEDIUM,
        confidence=0.79,  # < 0.80
        reasoning="Uncertain bug classification",
    )
    assert evaluate_guardrails(ticket, result) == "low_confidence"


def test_evaluate_guardrails_urgent_keyword_mismatch():
    ticket = Ticket(
        id="TCK-3",
        subject="Major outage",
        body="Our production database is completely down for all users.",
    )
    result_low = TriageResult(
        category=Category.TECHNICAL_BUG,
        priority=Priority.LOW,
        confidence=0.95,
        reasoning="Down issue classified as low priority",
    )
    assert evaluate_guardrails(ticket, result_low) == "urgent_keyword_mismatch"

    result_med = TriageResult(
        category=Category.TECHNICAL_BUG,
        priority=Priority.MEDIUM,
        confidence=0.95,
        reasoning="Down issue classified as medium priority",
    )
    assert evaluate_guardrails(ticket, result_med) == "urgent_keyword_mismatch"

    # High or Urgent with risky keywords should NOT trigger urgent_keyword_mismatch
    result_high = TriageResult(
        category=Category.TECHNICAL_BUG,
        priority=Priority.HIGH,
        confidence=0.95,
        reasoning="Proper high priority",
    )
    assert evaluate_guardrails(ticket, result_high) is None


def test_evaluate_guardrails_urgent_low_confidence():
    ticket = Ticket(
        id="TCK-4",
        subject="Critical security issue",
        body="Someone unauthorized seems to have accessed user records.",
    )
    result = TriageResult(
        category=Category.SECURITY_PRIVACY,
        priority=Priority.URGENT,
        confidence=0.89,  # urgent requires >= 0.90
        reasoning="Likely urgent breach but lower confidence",
    )
    assert evaluate_guardrails(ticket, result) == "urgent_low_confidence"


def test_evaluate_guardrails_clean_pass():
    ticket = Ticket(
        id="TCK-5",
        subject="Billing invoice question",
        body="Could you please send the invoice for last month's subscription?",
    )
    result = TriageResult(
        category=Category.BILLING,
        priority=Priority.LOW,
        confidence=0.88,
        reasoning="Standard billing request",
    )
    assert evaluate_guardrails(ticket, result) is None

