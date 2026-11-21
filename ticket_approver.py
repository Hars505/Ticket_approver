import concurrent.futures
import csv
import json
import os
import re
import sys
import urllib.request
from typing import Any, Callable, Iterable, Mapping, Optional


CONFIDENCE_THRESHOLD = 0.80

EMERGENCY_PATTERNS = (
    r"\bsystem\s+is\s+down\b",
    r"\bsystem\s+down\b",
    r"\bservice\s+is\s+down\b",
    r"\bservice\s+outage\b",
    r"\bcomplete\s+outage\b",
    r"\bproduction\s+is\s+down\b",
    r"\bhacked\b",
    r"\bsecurity\s+breach\b",
    r"\bdata\s+breach\b",
    r"\bransomware\b",
)


def ticket_text(ticket: Mapping[str, Any]) -> str:
    for key in ("text", "description", "message", "body", "ticket", "content"):
        if ticket.get(key) is not None:
            return str(ticket[key])
    subject = str(ticket.get("subject", "") or "")
    body = str(ticket.get("details", "") or "")
    return f"{subject} {body}".strip()


def normalize_confidence(value: Any) -> float:
    confidence = float(value)
    if confidence > 1:
        confidence /= 100.0
    return confidence


def ai_result(result: Any) -> Mapping[str, Any]:
    if isinstance(result, Mapping):
        return result
    category = getattr(result, "category", None)
    priority = getattr(result, "priority", None)
    confidence = getattr(result, "confidence", None)
    return {"category": category, "priority": priority, "confidence": confidence}


def emergency_ticket(text: str) -> bool:
    lowered = text.lower()
    return any(re.search(pattern, lowered, re.IGNORECASE) for pattern in EMERGENCY_PATTERNS)


def triage_ticket(
    ticket: Mapping[str, Any],
    classifier: Callable[[Mapping[str, Any]], Any],
    timeout: float = 10.0,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    text = ticket_text(ticket)
    reasons: list[str] = []
    result: Optional[Mapping[str, Any]] = None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(classifier, ticket)
            raw_result = future.result(timeout=timeout)
        result = ai_result(raw_result)
    except concurrent.futures.TimeoutError:
        reasons.append("timeout")
    except Exception as exc:
        reasons.append("api_error")

    if result is not None:
        try:
            confidence = normalize_confidence(result.get("confidence"))
        except (TypeError, ValueError):
            confidence = 0.0
            reasons.append("invalid_confidence")

        if confidence < confidence_threshold:
            reasons.append("low_confidence")

        priority = str(result.get("priority", "") or "").strip().lower()
        if emergency_ticket(text) and priority != "urgent":
            reasons.append("obvious_emergency")

    if reasons:
        pile = "human_review"
    else:
        pile = "auto_triaged"

    return {
        "ticket": ticket,
        "category": result.get("category") if result is not None else None,
        "priority": result.get("priority") if result is not None else None,
        "confidence": normalize_confidence(result["confidence"])
        if result is not None and result.get("confidence") is not None
        else None,
        "pile": pile,
        "reasons": reasons,
    }


def process_tickets(
    tickets: Iterable[Mapping[str, Any]],
    classifier: Callable[[Mapping[str, Any]], Any],
    timeout: float = 10.0,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> dict[str, Any]:
    results = [
        triage_ticket(ticket, classifier, timeout, confidence_threshold)
        for ticket in tickets
    ]
    auto = [item for item in results if item["pile"] == "auto_triaged"]
    human = [item for item in results if item["pile"] == "human_review"]
    reason_counts: dict[str, int] = {}
    for item in human:
        for reason in item["reasons"]:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "total": len(results),
        "auto_triaged": len(auto),
        "human_review": len(human),
        "reason_counts": reason_counts,
        "auto": auto,
        "human": human,
        "results": results,
    }


def load_tickets(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as source:
        if path.lower().endswith(".jsonl"):
            return [json.loads(line) for line in source if line.strip()]
        if path.lower().endswith(".csv"):
            return list(csv.DictReader(source))
        data = json.load(source)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and isinstance(data.get("tickets"), list):
        return data["tickets"]
    raise ValueError("JSON input must be a ticket array or an object with a 'tickets' array")


class HttpAiClassifier:
    def __init__(self, endpoint: str, api_key: Optional[str] = None, model: Optional[str] = None):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model

    def __call__(self, ticket: Mapping[str, Any]) -> Mapping[str, Any]:
        payload = {"ticket": ticket, "text": ticket_text(ticket)}
        if self.model:
            payload["model"] = self.model
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        request = urllib.request.Request(
            self.endpoint, data=body, headers=headers, method="POST"
        )
        with urllib.request.urlopen(request) as response:
            result = json.loads(response.read().decode("utf-8"))
        if not isinstance(result, dict):
            raise ValueError("AI response must be a JSON object")
        return result
