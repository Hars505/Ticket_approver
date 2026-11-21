import asyncio
import json
import math
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Optional
from pydantic import BaseModel, Field

from src.classifier import AsyncClassifier, ModelFailure
from src.guardrails import evaluate_guardrails, normalize_text
from src.loader import load_tickets
from src.schemas import Category, Priority, ReviewRecord, Ticket, TriageResult


class PipelineConfig(BaseModel):
    concurrency: int = 10
    output_dir: Path = Field(default_factory=lambda: Path("output"))
    timeout_seconds: float = 8.0


class PipelineResult(BaseModel):
    triaged: list[dict[str, Any]]
    human_review: list[dict[str, Any]]
    latencies: list[float]
    total_runtime_seconds: float
    report_text: str = ""


def _escape_markdown(text: str) -> str:
    """Escape markdown special characters for safe inclusion in tables and text."""
    if not text:
        return ""
    chars = ["|", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "<", ">"]
    res = str(text)
    for c in chars:
        res = res.replace(c, f"\\{c}")
    return res.replace("\n", " ").strip()


def _percentile(values: list[float], p: float) -> float:
    """Calculate percentile p (0-100) from sorted list using standard library."""
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_vals[int(k)]
    d0 = sorted_vals[int(f)] * (c - k)
    d1 = sorted_vals[int(c)] * (k - f)
    return d0 + d1


def render_report(result: PipelineResult) -> str:
    total = len(result.triaged) + len(result.human_review)
    triaged_count = len(result.triaged)
    review_count = len(result.human_review)
    triaged_pct = (triaged_count / total * 100) if total > 0 else 0.0
    review_pct = (review_count / total * 100) if total > 0 else 0.0

    # Latencies (non-zero latencies representing model calls)
    model_latencies = [l for l in result.latencies if l > 0.0]
    avg_latency = (sum(model_latencies) / len(model_latencies)) if model_latencies else 0.0
    p50_latency = _percentile(model_latencies, 50.0)
    p95_latency = _percentile(model_latencies, 95.0)

    # Category breakdown across triaged and model drafts
    cat_counts = {cat.value: 0 for cat in Category}
    for item in result.triaged:
        cat_counts[item["triage"]["category"]] += 1
    for item in result.human_review:
        if item.get("model_draft") and item["model_draft"].get("category"):
            cat_val = item["model_draft"]["category"]
            if cat_val in cat_counts:
                cat_counts[cat_val] += 1

    # Priority breakdown across triaged and model drafts
    prio_counts = {prio.value: 0 for prio in Priority}
    for item in result.triaged:
        prio_counts[item["triage"]["priority"]] += 1
    for item in result.human_review:
        if item.get("model_draft") and item["model_draft"].get("priority"):
            prio_val = item["model_draft"]["priority"]
            if prio_val in prio_counts:
                prio_counts[prio_val] += 1

    # Escalation reasons
    standard_reasons = [
        "invalid_input",
        "insufficient_context",
        "low_confidence",
        "urgent_keyword_mismatch",
        "urgent_low_confidence",
        "model_unavailable",
        "invalid_schema",
    ]
    reason_counts = {r: 0 for r in standard_reasons}
    for item in result.human_review:
        reason = item.get("escalation_reason", "unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    lines = [
        "# Support Ticket Triage Operational Report",
        "",
        "## Summary Metrics",
        "",
        f"- **Total Tickets Processed**: {total}",
        f"- **Automatically Triaged**: {triaged_count} ({triaged_pct:.1f}%)",
        f"- **Routed to Human Review**: {review_count} ({review_pct:.1f}%)",
        f"- **Total Pipeline Runtime**: {result.total_runtime_seconds:.2f}s",
        f"- **Average Model Latency**: {avg_latency:.1f} ms",
        f"- **p50 Model Latency**: {p50_latency:.1f} ms",
        f"- **p95 Model Latency**: {p95_latency:.1f} ms",
        "",
        "## Classification Taxonomy Breakdown",
        "",
        "| Category | Count | Percentage |",
        "| :--- | :--- | :--- |",
    ]
    total_cats = sum(cat_counts.values())
    for cat, count in cat_counts.items():
        pct = (count / total_cats * 100) if total_cats > 0 else 0.0
        lines.append(f"| `{cat}` | {count} | {pct:.1f}% |")

    lines.extend([
        "",
        "## Priority Distribution",
        "",
        "| Priority | Count | Percentage |",
        "| :--- | :--- | :--- |",
    ])
    total_prios = sum(prio_counts.values())
    for prio, count in prio_counts.items():
        pct = (count / total_prios * 100) if total_prios > 0 else 0.0
        lines.append(f"| `{prio}` | {count} | {pct:.1f}% |")

    lines.extend([
        "",
        "## Escalation Reasons Breakdown",
        "",
        "| Escalation Reason | Count |",
        "| :--- | :--- |",
    ])
    for reason, count in reason_counts.items():
        lines.append(f"| `{reason}` | {count} |")

    # Sample tickets (3-5 samples)
    lines.extend([
        "",
        "## Sample Ticket Processing Inspection",
        "",
    ])

    sample_items = (result.triaged[:3] if result.triaged else []) + (result.human_review[:2] if result.human_review else [])
    for idx, sample in enumerate(sample_items[:5], 1):
        if "triage" in sample:
            t = sample["ticket"]
            tr = sample["triage"]
            cat_str = tr.get('category').value if hasattr(tr.get('category'), 'value') else str(tr.get('category', ''))
            prio_str = tr.get('priority').value if hasattr(tr.get('priority'), 'value') else str(tr.get('priority', ''))
            lines.extend([
                f"### Sample {idx}: Triaged (`{_escape_markdown(t.get('id', 'N/A'))}`)",
                f"- **Subject**: {_escape_markdown(t.get('subject', ''))}",
                f"- **Category / Priority**: `{cat_str}` / `{prio_str}` (Confidence: {tr.get('confidence')})",
                f"- **Reasoning**: {_escape_markdown(tr.get('reasoning', ''))}",
                "",
            ])
        else:
            t_id = sample.get("ticket_id") or "N/A"
            reason = sample.get("escalation_reason", "unknown")
            t_sub = sample.get("ticket", {}).get("subject") if sample.get("ticket") else ""
            lines.extend([
                f"### Sample {idx}: Human Review (`{_escape_markdown(t_id)}`)",
                f"- **Escalation Reason**: `{reason}`",
                f"- **Subject**: {_escape_markdown(t_sub)}",
                "",
            ])

    return "\n".join(lines) + "\n"


def _atomic_write_file(target_path: Path, content: str) -> None:
    """Atomically write content to target_path via temporary file and replace."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = target_path.parent
    fd, temp_file_path = tempfile.mkstemp(dir=temp_dir, prefix="triage_atomic_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(temp_file_path, target_path)
    except Exception:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise


async def _process_ticket(
    index: int,
    item: Ticket | ReviewRecord,
    classifier: AsyncClassifier,
    semaphore: asyncio.Semaphore,
) -> tuple[int, str, dict[str, Any], float]:
    """Process a single ticket or pre-escalated row, returning (index, routing, payload, latency_ms)."""
    if isinstance(item, ReviewRecord):
        return (index, "human_review", item.model_dump(), 0.0)

    # Check insufficient context before invoking model
    if len(normalize_text(item.body)) < 15:
        rec = ReviewRecord(
            ticket_id=item.id,
            ticket=item,
            raw_data=item.model_dump(),
            escalation_reason="insufficient_context",
            latency_ms=0.0,
            metadata=item.metadata,
        )
        return (index, "human_review", rec.model_dump(), 0.0)

    # Bounded model invocation
    async with semaphore:
        start = time.perf_counter()
        try:
            result = await classifier.classify(item)
        except Exception as exc:
            result = ModelFailure(
                escalation_reason="model_unavailable",
                error_message=f"Classifier raised unhandled error: {exc}",
            )
        latency_ms = round((time.perf_counter() - start) * 1000.0, 2)

    if isinstance(result, ModelFailure):
        rec = ReviewRecord(
            ticket_id=item.id,
            ticket=item,
            raw_data=item.model_dump(),
            escalation_reason=result.escalation_reason,
            latency_ms=latency_ms,
            metadata={**item.metadata, "error": result.error_message},
        )
        return (index, "human_review", rec.model_dump(), latency_ms)

    # Apply deterministic safety guardrails
    reason = evaluate_guardrails(item, result)
    if reason is not None:
        rec = ReviewRecord(
            ticket_id=item.id,
            ticket=item,
            raw_data=item.model_dump(),
            model_draft=result,
            escalation_reason=reason,
            latency_ms=latency_ms,
            metadata=item.metadata,
        )
        return (index, "human_review", rec.model_dump(), latency_ms)

    # Passed all guardrails -> Triaged
    triaged_payload = {
        "ticket": item.model_dump(),
        "triage": result.model_dump(),
        "latency_ms": latency_ms,
    }
    return (index, "triaged", triaged_payload, latency_ms)


async def run_pipeline(
    input_path: Path | str,
    output_dir: Path | str,
    classifier: AsyncClassifier,
    concurrency: int = 10,
) -> PipelineResult:
    """Run end-to-end triage pipeline with bounded concurrency, atomic outputs, and invariant enforcement."""
    start_time = time.perf_counter()
    out_dir = Path(output_dir)
    items = load_tickets(input_path)

    semaphore = asyncio.Semaphore(concurrency)
    tasks = [
        _process_ticket(idx, item, classifier, semaphore)
        for idx, item in enumerate(items)
    ]
    raw_results = await asyncio.gather(*tasks)

    # Sort results back to exact input order
    raw_results.sort(key=lambda r: r[0])

    triaged: list[dict[str, Any]] = []
    human_review: list[dict[str, Any]] = []
    latencies: list[float] = []

    for _, routing, payload, latency in raw_results:
        latencies.append(latency)
        if routing == "triaged":
            triaged.append(payload)
        else:
            human_review.append(payload)

    total_runtime = round(time.perf_counter() - start_time, 2)

    result = PipelineResult(
        triaged=triaged,
        human_review=human_review,
        latencies=latencies,
        total_runtime_seconds=total_runtime,
    )
    result.report_text = render_report(result)

    # Write atomic outputs
    _atomic_write_file(out_dir / "triaged.json", json.dumps(result.triaged, indent=2))
    _atomic_write_file(out_dir / "human_review.json", json.dumps(result.human_review, indent=2))
    _atomic_write_file(out_dir / "report.md", result.report_text)

    return result

