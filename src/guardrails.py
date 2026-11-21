import re
from src.loader import normalize_html_and_whitespace
from src.schemas import Priority, Ticket, TriageResult

RISK_KEYWORDS = [
    "outage",
    "down",
    "production",
    "breach",
    "hacked",
    "unauthorized",
    "fraud",
    "chargeback",
    "data loss",
    "lawsuit",
    "can't login",
]

# Build compiled regex patterns for keyword matching with word boundaries
_PATTERNS = [
    re.compile(r"\bcan['’]?t\s+login\b", re.IGNORECASE),
    re.compile(r"\bdata\s+loss\b", re.IGNORECASE),
] + [
    re.compile(rf"\b{re.escape(kw)}\b", re.IGNORECASE)
    for kw in RISK_KEYWORDS
    if kw not in ("can't login", "data loss")
]


def normalize_text(value: str) -> str:
    """Normalize text by stripping HTML, collapsing whitespace, and lowercasing."""
    cleaned = normalize_html_and_whitespace(value)
    return cleaned.lower()


def has_urgent_keyword(text: str) -> bool:
    """Check if any risk keyword matches the text case-insensitively with word boundaries."""
    norm = normalize_text(text)
    return any(p.search(norm) is not None for p in _PATTERNS)


def evaluate_guardrails(ticket: Ticket, result: TriageResult) -> str | None:
    """Evaluate deterministic guardrails against the ticket and model triage result.

    Order of checks:
    1. insufficient_context: normalized body < 15 characters
    2. low_confidence: confidence < 0.80
    3. urgent_keyword_mismatch: risky keyword present, but priority is medium or low
    4. urgent_low_confidence: priority is urgent, but confidence < 0.90

    Returns escalation reason string or None if valid.
    """
    # 1. Insufficient context check
    if len(normalize_text(ticket.body)) < 15:
        return "insufficient_context"

    # 2. Low confidence check
    if result.confidence < 0.80:
        return "low_confidence"

    # 3. Urgent keyword mismatch check
    full_text = f"{ticket.subject} {ticket.body}"
    if has_urgent_keyword(full_text) and result.priority in (Priority.MEDIUM, Priority.LOW):
        return "urgent_keyword_mismatch"

    # 4. Urgent low confidence check
    if result.priority == Priority.URGENT and result.confidence < 0.90:
        return "urgent_low_confidence"

    return None
