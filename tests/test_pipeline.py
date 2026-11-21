import asyncio
import json
from pathlib import Path
import pytest

from src.classifier import AsyncClassifier, ClassifierConfig, ModelFailure
from src.schemas import Category, Priority, Ticket, TriageResult
from src.pipeline import (
    PipelineConfig,
    PipelineResult,
    run_pipeline,
    render_report,
)


class MockClassifier(AsyncClassifier):
    def __init__(self, responses: dict[str, TriageResult | ModelFailure]):
        self.responses = responses
        self.concurrency_peak = 0
        self._current_concurrency = 0
        self.calls = []

    async def classify(self, ticket: Ticket) -> TriageResult | ModelFailure:
        self._current_concurrency += 1
        if self._current_concurrency > self.concurrency_peak:
            self.concurrency_peak = self._current_concurrency
        self.calls.append(ticket.id)
        await asyncio.sleep(0.01)
        res = self.responses.get(
            ticket.id,
            TriageResult(
                category=Category.GENERAL_INQUIRY,
                priority=Priority.LOW,
                confidence=0.9,
                reasoning="Default mock triage",
            ),
        )
        self._current_concurrency -= 1
        return res


def test_pipeline_execution_and_invariants(tmp_path: Path):
    input_file = tmp_path / "tickets.json"
    output_dir = tmp_path / "output"

    input_data = [
        # 1. Clean valid ticket -> triaged
        {
            "id": "TCK-1",
            "subject": "Billing inquiry",
            "body": "Can you please send me the receipt for my annual subscription payment?",
        },
        # 2. Low confidence -> human_review (low_confidence)
        {
            "id": "TCK-2",
            "subject": "Vague question",
            "body": "It seems like something is not functioning properly on the page.",
        },
        # 3. Urgent risk keyword with low priority -> human_review (urgent_keyword_mismatch)
        {
            "id": "TCK-3",
            "subject": "Major outage",
            "body": "Our production database is completely down and inaccessible.",
        },
        # 4. Short body (< 15 chars) -> human_review (insufficient_context, bypassed model)
        {
            "id": "TCK-4",
            "subject": "Need help",
            "body": "Help me",
        },
        # 5. Model failure -> human_review (model_unavailable)
        {
            "id": "TCK-5",
            "subject": "API issue",
            "body": "Getting 500 error on the REST API endpoint repeatedly.",
        },
        # 6. Malformed input row -> human_review (invalid_input)
        {
            "id": "TCK-6",
            # missing body
        },
    ]
    input_file.write_text(json.dumps(input_data))

    mock_responses = {
        "TCK-1": TriageResult(
            category=Category.BILLING,
            priority=Priority.LOW,
            confidence=0.92,
            reasoning="Valid billing receipt request",
        ),
        "TCK-2": TriageResult(
            category=Category.GENERAL_INQUIRY,
            priority=Priority.LOW,
            confidence=0.72,  # < 0.80 -> low_confidence
            reasoning="Low confidence inquiry",
        ),
        "TCK-3": TriageResult(
            category=Category.TECHNICAL_BUG,
            priority=Priority.LOW,  # risky text with low priority -> urgent_keyword_mismatch
            confidence=0.95,
            reasoning="Treated as low priority bug",
        ),
        "TCK-5": ModelFailure(
            escalation_reason="model_unavailable",
            error_message="Simulated endpoint timeout",
        ),
    }

    classifier = MockClassifier(mock_responses)
    result = asyncio.run(run_pipeline(
        input_path=input_file,
        output_dir=output_dir,
        classifier=classifier,
        concurrency=2,
    ))

    # Invariant 1: Total records match input
    assert len(result.triaged) + len(result.human_review) == len(input_data)
    assert len(result.triaged) == 1
    assert len(result.human_review) == 5

    # Short body ticket (TCK-4) should NOT have called classifier
    assert "TCK-4" not in classifier.calls
    # Malformed row (TCK-6) should NOT have called classifier
    assert "TCK-6" not in classifier.calls

    # Verify escalation reasons
    reasons = {r["ticket_id"]: r["escalation_reason"] for r in result.human_review}
    assert reasons["TCK-2"] == "low_confidence"
    assert reasons["TCK-3"] == "urgent_keyword_mismatch"
    assert reasons["TCK-4"] == "insufficient_context"
    assert reasons["TCK-5"] == "model_unavailable"
    assert reasons["TCK-6"] == "invalid_input"

    # Concurrency bounded by 2
    assert classifier.concurrency_peak <= 2

    # Check output files written
    triaged_file = output_dir / "triaged.json"
    review_file = output_dir / "human_review.json"
    report_file = output_dir / "report.md"

    assert triaged_file.exists()
    assert review_file.exists()
    assert report_file.exists()

    saved_triaged = json.loads(triaged_file.read_text())
    assert len(saved_triaged) == 1
    assert saved_triaged[0]["ticket"]["id"] == "TCK-1"

    report_text = report_file.read_text()
    assert "Total Tickets" in report_text or "Total input" in report_text or "Total" in report_text
    assert "Triaged" in report_text
    assert "Human Review" in report_text
    assert "p50" in report_text or "P50" in report_text
    assert "p95" in report_text or "P95" in report_text
    assert "billing" in report_text
    assert "insufficient_context" in report_text

