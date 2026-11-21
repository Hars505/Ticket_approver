import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
import httpx
from pydantic import BaseModel, Field

from src.classifier import AsyncClassifier, ClassifierConfig, OfflineClassifier
from src.guardrails import RISK_KEYWORDS, evaluate_guardrails, normalize_text
from src.loader import load_tickets, normalize_html_and_whitespace
from src.pipeline import _atomic_write_file, render_report, run_pipeline
from src.schemas import Category, Priority, ReviewRecord, Ticket, TriageResult

load_dotenv()

app = FastAPI(
    title="Support Ticket Triage API",
    description="REST API backend for Support Ticket Triage Console with live classification and queue management.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = Path("data")
OUTPUT_DIR = Path("output")
TRIAGED_PATH = OUTPUT_DIR / "triaged.json"
REVIEW_PATH = OUTPUT_DIR / "human_review.json"
REPORT_PATH = OUTPUT_DIR / "report.md"
TICKETS_PATH = DATA_DIR / "tickets.json"

# In-memory settings state
runtime_settings = {
    "threshold": 0.80,
    "chaos": 0.0,
    "risk_keywords": list(RISK_KEYWORDS),
}


def _read_json_safe(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def _format_triaged(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    for item in items:
        t = item.get("ticket", {})
        tr = item.get("triage", {})
        formatted.append({
            "id": t.get("id", "N/A"),
            "subject": t.get("subject", ""),
            "body": t.get("body", ""),
            "category": tr.get("category"),
            "priority": tr.get("priority"),
            "confidence": tr.get("confidence"),
            "latency": item.get("latency_ms", 0),
            "reasoning": tr.get("reasoning", ""),
            "escalation_reason": None,
            "created_at": t.get("created_at"),
            "metadata": t.get("metadata", {}),
        })
    return formatted


def _format_review(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formatted = []
    for item in items:
        t = item.get("ticket") or item.get("raw_data") or {}
        draft = item.get("model_draft") or {}
        t_id = item.get("ticket_id") or t.get("id") or "N/A"
        formatted.append({
            "id": t_id,
            "subject": t.get("subject", ""),
            "body": t.get("body", "") if isinstance(t, dict) else str(t),
            "category": draft.get("category"),
            "priority": draft.get("priority"),
            "confidence": draft.get("confidence"),
            "latency": item.get("latency_ms", 0),
            "reasoning": draft.get("reasoning"),
            "escalation_reason": item.get("escalation_reason", "unknown"),
            "error": item.get("metadata", {}).get("error") if isinstance(item.get("metadata"), dict) else None,
            "created_at": t.get("created_at") if isinstance(t, dict) else None,
            "metadata": item.get("metadata", {}),
        })
    return formatted


from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path("frontend/dist")
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/", include_in_schema=False)
    async def serve_frontend():
        return FileResponse(FRONTEND_DIST / "index.html")


@app.get("/api/health")
async def health_check():
    api_key = os.getenv("LLM_API_KEY", "")
    has_key = bool(api_key and not api_key.startswith("your_"))
    return {
        "status": "healthy",
        "has_api_key": has_key,
        "model": os.getenv("LLM_MODEL", "gemini-1.5-flash"),
        "provider_url": os.getenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
    }


@app.get("/api/overview")
async def get_overview():
    triaged_raw = _read_json_safe(TRIAGED_PATH)
    review_raw = _read_json_safe(REVIEW_PATH)

    # If outputs are missing, run an initial offline pass so frontend has real data
    if not triaged_raw and not review_raw and TICKETS_PATH.exists():
        classifier = OfflineClassifier()
        await run_pipeline(TICKETS_PATH, OUTPUT_DIR, classifier, concurrency=10)
        triaged_raw = _read_json_safe(TRIAGED_PATH)
        review_raw = _read_json_safe(REVIEW_PATH)

    triaged_list = _format_triaged(triaged_raw)
    review_list = _format_review(review_raw)

    total = len(triaged_list) + len(review_list)
    auto_count = len(triaged_list)
    human_count = len(review_list)

    # Latencies
    latencies = [
        float(t["latency"])
        for t in triaged_list
        if t.get("latency") is not None and float(t["latency"]) > 0
    ] + [
        float(r["latency"])
        for r in review_list
        if r.get("latency") is not None and float(r["latency"]) > 0
    ]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0.0
    sorted_lat = sorted(latencies)
    p95_latency = round(sorted_lat[int(len(sorted_lat) * 0.95)], 1) if sorted_lat else 0.0

    # Category counts
    cat_order = [
        ("Billing", "billing"),
        ("Technical bug", "technical_bug"),
        ("Account access", "account_access"),
        ("Security & privacy", "security_privacy"),
        ("Feature request", "feature_request"),
        ("General inquiry", "general_inquiry"),
    ]
    category_counts = {k: 0 for _, k in cat_order}
    for t in triaged_list:
        if t["category"] in category_counts:
            category_counts[t["category"]] += 1
    for r in review_list:
        if r["category"] in category_counts:
            category_counts[r["category"]] += 1

    category_data = [[label, category_counts[k], k] for label, k in cat_order]

    # Priority counts
    prio_counts = {"urgent": 0, "high": 0, "medium": 0, "low": 0}
    for t in triaged_list:
        if t["priority"] in prio_counts:
            prio_counts[t["priority"]] += 1
    for r in review_list:
        if r["priority"] in prio_counts:
            prio_counts[r["priority"]] += 1

    # Escalation reason counts
    escalation_counts = {
        "low_confidence": 0,
        "urgent_keyword_mismatch": 0,
        "model_unavailable": 0,
        "insufficient_context": 0,
        "invalid_input": 0,
        "invalid_schema": 0,
    }
    for r in review_list:
        reason = r.get("escalation_reason") or "other"
        escalation_counts[reason] = escalation_counts.get(reason, 0) + 1

    return {
        "total": total,
        "autoCount": auto_count,
        "humanReviewCount": human_count,
        "avgLatency": avg_latency,
        "p95Latency": p95_latency,
        "totalRuntime": 0.08,
        "categoryData": category_data,
        "priorities": prio_counts,
        "escalationReasons": escalation_counts,
    }


@app.get("/api/tickets/triaged")
async def get_triaged_tickets(
    search: str = Query("", description="Search in ID, subject, or body"),
    category: str = Query("all", description="Category filter"),
    priority: str = Query("all", description="Priority filter"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    triaged_raw = _read_json_safe(TRIAGED_PATH)
    items = _format_triaged(triaged_raw)

    filtered = items
    if search:
        s = search.lower()
        filtered = [t for t in filtered if s in t["id"].lower() or s in t["subject"].lower() or s in t["body"].lower()]
    if category != "all":
        filtered = [t for t in filtered if t["category"] == category]
    if priority != "all":
        filtered = [t for t in filtered if t["priority"] == priority]

    total = len(filtered)
    paginated = filtered[offset : offset + limit]
    return {"total": total, "tickets": paginated}


@app.get("/api/tickets/review")
async def get_review_tickets(
    search: str = Query("", description="Search in ID, subject, or body"),
    filter: str = Query("all", description="Escalation reason filter"),
    limit: int = Query(500, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    review_raw = _read_json_safe(REVIEW_PATH)
    items = _format_review(review_raw)

    filtered = items
    if search:
        s = search.lower()
        filtered = [t for t in filtered if s in t["id"].lower() or s in t["subject"].lower() or s in t["body"].lower()]
    if filter != "all":
        filtered = [t for t in filtered if t["escalation_reason"] == filter]

    total = len(filtered)
    paginated = filtered[offset : offset + limit]
    return {"total": total, "tickets": paginated}


class ApproveRequest(BaseModel):
    category: Category
    priority: Priority
    notes: Optional[str] = None


@app.post("/api/tickets/{ticket_id}/approve")
async def approve_ticket(ticket_id: str, payload: ApproveRequest):
    """Approve a ticket from human review and move it to triaged."""
    review_raw = _read_json_safe(REVIEW_PATH)
    triaged_raw = _read_json_safe(TRIAGED_PATH)

    match_idx = -1
    matched_item = None
    for idx, item in enumerate(review_raw):
        t_id = item.get("ticket_id") or (item.get("ticket", {}) or {}).get("id")
        if t_id == ticket_id:
            match_idx = idx
            matched_item = item
            break

    if match_idx == -1 or matched_item is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found in review queue")

    # Remove from review
    review_raw.pop(match_idx)

    # Reconstruct ticket model
    orig_ticket = matched_item.get("ticket") or matched_item.get("raw_data") or {}
    triage_info = {
        "category": payload.category.value,
        "priority": payload.priority.value,
        "confidence": 1.0,
        "reasoning": payload.notes or "Manually approved by human reviewer.",
    }
    triaged_item = {
        "ticket": {
            "id": ticket_id,
            "subject": orig_ticket.get("subject", ""),
            "body": orig_ticket.get("body", ""),
            "created_at": orig_ticket.get("created_at"),
            "metadata": orig_ticket.get("metadata", {}),
        },
        "triage": triage_info,
        "latency_ms": matched_item.get("latency_ms", 0.0),
    }

    triaged_raw.append(triaged_item)

    # Save atomically
    _atomic_write_file(REVIEW_PATH, json.dumps(review_raw, indent=2))
    _atomic_write_file(TRIAGED_PATH, json.dumps(triaged_raw, indent=2))

    return {"success": True, "ticket_id": ticket_id, "moved_to": "triaged"}


@app.post("/api/tickets/{ticket_id}/flag")
async def flag_ticket_for_review(ticket_id: str, reason: str = Query("human_flagged")):
    """Move a triaged ticket back to the human review queue."""
    triaged_raw = _read_json_safe(TRIAGED_PATH)
    review_raw = _read_json_safe(REVIEW_PATH)

    match_idx = -1
    matched_item = None
    for idx, item in enumerate(triaged_raw):
        t_id = (item.get("ticket", {}) or {}).get("id")
        if t_id == ticket_id:
            match_idx = idx
            matched_item = item
            break

    if match_idx == -1 or matched_item is None:
        raise HTTPException(status_code=404, detail=f"Ticket {ticket_id} not found in triaged queue")

    triaged_raw.pop(match_idx)

    t = matched_item.get("ticket", {})
    tr = matched_item.get("triage", {})
    review_record = {
        "ticket_id": ticket_id,
        "ticket": t,
        "raw_data": t,
        "model_draft": tr,
        "escalation_reason": reason,
        "latency_ms": matched_item.get("latency_ms", 0.0),
        "metadata": t.get("metadata", {}),
    }

    review_raw.append(review_record)

    _atomic_write_file(TRIAGED_PATH, json.dumps(triaged_raw, indent=2))
    _atomic_write_file(REVIEW_PATH, json.dumps(review_raw, indent=2))

    return {"success": True, "ticket_id": ticket_id, "moved_to": "human_review"}


class RunPipelineRequest(BaseModel):
    offline: Optional[bool] = None
    concurrency: int = 10
    simulate_failures: float = Field(0.0, ge=0.0, le=1.0)
    threshold: float = Field(0.80, ge=0.5, le=1.0)


@app.post("/api/triage/run")
async def trigger_triage_run(payload: RunPipelineRequest):
    """Trigger an asynchronous triage pipeline run."""
    api_key = os.getenv("LLM_API_KEY", "")
    base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")

    use_offline = payload.offline if payload.offline is not None else (not api_key or api_key.startswith("your_"))

    runtime_settings["threshold"] = payload.threshold
    runtime_settings["chaos"] = payload.simulate_failures

    input_path = TICKETS_PATH
    if not input_path.exists():
        raise HTTPException(status_code=404, detail="Default tickets dataset not found at data/tickets.json")

    if use_offline:
        classifier = OfflineClassifier(failure_rate=payload.simulate_failures)
        res = await run_pipeline(
            input_path=input_path,
            output_dir=OUTPUT_DIR,
            classifier=classifier,
            concurrency=payload.concurrency,
        )
    else:
        config = ClassifierConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        async with httpx.AsyncClient() as client:
            classifier = AsyncClassifier(
                client=client,
                config=config,
                failure_rate=payload.simulate_failures,
                fallback_on_rate_limit=True,
            )
            res = await run_pipeline(
                input_path=input_path,
                output_dir=OUTPUT_DIR,
                classifier=classifier,
                concurrency=payload.concurrency,
            )

    return {
        "status": "completed",
        "mode": "offline" if use_offline else "online",
        "total": len(res.triaged) + len(res.human_review),
        "triaged": len(res.triaged),
        "human_review": len(res.human_review),
        "runtime_seconds": res.total_runtime_seconds,
    }


class SingleTicketRequest(BaseModel):
    id: Optional[str] = None
    subject: str
    body: str
    offline: Optional[bool] = None


@app.post("/api/triage/single")
async def triage_single_ticket(payload: SingleTicketRequest):
    """Triage a single ticket in real time."""
    norm_subject = normalize_html_and_whitespace(payload.subject)
    norm_body = normalize_html_and_whitespace(payload.body)
    ticket_id = payload.id or f"LIVE-{os.urandom(3).hex().upper()}"

    ticket = Ticket(
        id=ticket_id,
        subject=norm_subject,
        body=norm_body,
    )

    # Check context guardrail
    if len(normalize_text(ticket.body)) < 15:
        return {
            "ticket_id": ticket.id,
            "triaged": False,
            "escalation_reason": "insufficient_context",
            "message": "Ticket body contains insufficient context (< 15 characters).",
        }

    api_key = os.getenv("LLM_API_KEY", "")
    use_offline = (
        payload.offline
        if payload.offline is not None
        else (not api_key or api_key.startswith("your_"))
    )

    if use_offline:
        classifier = OfflineClassifier()
        result = await classifier.classify(ticket)
    else:
        config = ClassifierConfig(
            api_key=api_key,
            base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        )
        async with httpx.AsyncClient() as client:
            classifier = AsyncClassifier(client=client, config=config)
            result = await classifier.classify(ticket)

    if isinstance(result, TriageResult):
        reason = evaluate_guardrails(ticket, result)
        if reason:
            return {
                "ticket_id": ticket.id,
                "triaged": False,
                "escalation_reason": reason,
                "model_draft": result.model_dump(),
            }
        return {
            "ticket_id": ticket.id,
            "triaged": True,
            "escalation_reason": None,
            "triage": result.model_dump(),
        }
    else:
        return {
            "ticket_id": ticket.id,
            "triaged": False,
            "escalation_reason": result.escalation_reason,
            "error": result.error_message,
        }


@app.get("/api/report/download")
async def download_report():
    if not REPORT_PATH.exists():
        raise HTTPException(status_code=404, detail="Report not generated yet.")
    return FileResponse(
        REPORT_PATH,
        media_type="text/markdown",
        filename="ticket_triage_report.md",
    )


@app.post("/api/upload")
async def upload_tickets_batch(file: UploadFile = File(...)):
    """Upload a new JSON or CSV batch file and run the triage pipeline."""
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".json", ".csv"):
        raise HTTPException(status_code=400, detail="Only .json or .csv files are supported")

    upload_path = DATA_DIR / f"uploaded_{file.filename}"
    upload_path.parent.mkdir(parents=True, exist_ok=True)

    with upload_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Run triage on uploaded file
    classifier = OfflineClassifier()
    res = await run_pipeline(upload_path, OUTPUT_DIR, classifier, concurrency=10)

    return {
        "status": "success",
        "filename": file.filename,
        "total_tickets": len(res.triaged) + len(res.human_review),
        "triaged": len(res.triaged),
        "human_review": len(res.human_review),
    }


@app.get("/api/settings")
async def get_settings():
    return runtime_settings


@app.post("/api/settings")
async def update_settings(payload: dict[str, Any]):
    if "threshold" in payload:
        runtime_settings["threshold"] = float(payload["threshold"])
    if "chaos" in payload:
        runtime_settings["chaos"] = float(payload["chaos"])
    if "risk_keywords" in payload and isinstance(payload["risk_keywords"], list):
        runtime_settings["risk_keywords"] = payload["risk_keywords"]
    return {"status": "saved", "settings": runtime_settings}
