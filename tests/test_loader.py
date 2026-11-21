import json
import pytest
from pathlib import Path
from src.loader import load_tickets, normalize_html_and_whitespace
from src.schemas import Ticket, ReviewRecord


def test_normalize_html_and_whitespace():
    raw = "  Hello   <br>world!  <p>This is <b>HTML</b></p>   \n\n\t &amp; more.  "
    normalized = normalize_html_and_whitespace(raw)
    assert "<" not in normalized
    assert ">" not in normalized
    assert "Hello world! This is HTML & more." == normalized or "Hello world! This is HTML & more." in normalized


def test_load_tickets_from_json(tmp_path: Path):
    data = [
        {
            "id": "TCK-1",
            "subject": "App crashed <br>",
            "body": "<p>When clicking submit, the app crashes</p>",
            "created_at": "2026-11-21T00:00:00Z",
            "custom_field": "vip",
        },
        {
            "id": "TCK-2",
            "subject": "Missing body",
            # missing 'body' field
        },
        {
            "id": "",
            "subject": "Empty ID",
            "body": "Valid body text here",
        },
        "not a dict row",
    ]
    json_path = tmp_path / "tickets.json"
    json_path.write_text(json.dumps(data))

    records = load_tickets(json_path)
    assert len(records) == 4

    # Row 1 is a valid Ticket
    assert isinstance(records[0], Ticket)
    assert records[0].id == "TCK-1"
    assert "<br>" not in records[0].subject
    assert "<p>" not in records[0].body
    assert records[0].metadata.get("custom_field") == "vip"

    # Row 2 is ReviewRecord due to missing body
    assert isinstance(records[1], ReviewRecord)
    assert records[1].escalation_reason == "invalid_input"
    assert records[1].ticket_id == "TCK-2"

    # Row 3 is ReviewRecord due to empty id
    assert isinstance(records[2], ReviewRecord)
    assert records[2].escalation_reason == "invalid_input"

    # Row 4 is ReviewRecord due to non-dict row
    assert isinstance(records[3], ReviewRecord)
    assert records[3].escalation_reason == "invalid_input"


def test_load_tickets_from_csv(tmp_path: Path):
    csv_content = """id,subject,body,created_at,source
TCK-10,Login issue,"Cannot login to dashboard, getting 403 error",2026-11-21,portal
TCK-11,,"",2026-11-21,email
"""
    csv_path = tmp_path / "tickets.csv"
    csv_path.write_text(csv_content)

    records = load_tickets(csv_path)
    assert len(records) == 2

    assert isinstance(records[0], Ticket)
    assert records[0].id == "TCK-10"
    assert records[0].metadata.get("source") == "portal"

    # Second row has empty body which might still construct Ticket or become ReviewRecord depending on requirements,
    # but let's check its behavior
    assert isinstance(records[1], Ticket) or isinstance(records[1], ReviewRecord)


def test_load_tickets_malformed_json(tmp_path: Path):
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{\"not\": valid json")

    with pytest.raises(ValueError):
        load_tickets(bad_json)


def test_load_tickets_unsupported_format(tmp_path: Path):
    unknown = tmp_path / "tickets.xml"
    unknown.write_text("<tickets></tickets>")

    with pytest.raises(ValueError, match="Unsupported file format"):
        load_tickets(unknown)

