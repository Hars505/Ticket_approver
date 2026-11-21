import csv
import html
import json
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.schemas import Ticket, ReviewRecord


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_html_and_whitespace(text: str) -> str:
    """Strip HTML tags, unescape HTML entities, and collapse multiple whitespace characters."""
    if not text:
        return ""
    # Unescape entities first or after tag removal
    cleaned = _HTML_TAG_RE.sub(" ", text)
    cleaned = html.unescape(cleaned)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _parse_row(row: Any, row_idx: int) -> Ticket | ReviewRecord:
    if not isinstance(row, dict):
        return ReviewRecord(
            ticket_id=None,
            raw_data=row,
            escalation_reason="invalid_input",
            metadata={"row_index": row_idx, "error": "Row is not a dictionary"},
        )

    ticket_id = str(row.get("id", "")).strip() if "id" in row and row.get("id") is not None else None
    subject = str(row.get("subject", "") or "")
    body_val = row.get("body")
    created_at = str(row.get("created_at")) if row.get("created_at") is not None else None

    # Check known keys and collect rest in metadata
    known_keys = {"id", "subject", "body", "created_at"}
    extra_metadata = {k: v for k, v in row.items() if k not in known_keys}

    if body_val is None:
        return ReviewRecord(
            ticket_id=ticket_id,
            raw_data=row,
            escalation_reason="invalid_input",
            metadata={"row_index": row_idx, "error": "Missing 'body' field", **extra_metadata},
        )

    norm_subject = normalize_html_and_whitespace(subject)
    norm_body = normalize_html_and_whitespace(str(body_val))

    try:
        return Ticket(
            id=ticket_id or "",
            subject=norm_subject,
            body=norm_body,
            created_at=created_at,
            metadata=extra_metadata,
        )
    except (ValidationError, ValueError) as err:
        return ReviewRecord(
            ticket_id=ticket_id,
            raw_data=row,
            escalation_reason="invalid_input",
            metadata={"row_index": row_idx, "error": str(err), **extra_metadata},
        )


def load_tickets(path: Path | str) -> list[Ticket | ReviewRecord]:
    """Load tickets from a JSON or CSV file, returning a list of Ticket or ReviewRecord instances."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with file_path.open("r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError as err:
                raise ValueError(f"Malformed JSON in input file: {err}") from err

        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON list of ticket objects, got {type(data).__name__}")

        return [_parse_row(row, idx) for idx, row in enumerate(data)]

    elif suffix == ".csv":
        results: list[Ticket | ReviewRecord] = []
        with file_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader):
                results.append(_parse_row(dict(row), idx))
        return results

    else:
        raise ValueError(f"Unsupported file format: {suffix}. Must be .json or .csv")
