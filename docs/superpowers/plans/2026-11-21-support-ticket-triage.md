# Support Ticket Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a provider-neutral, fail-safe async Python service that classifies 300 support tickets, routes every record to triaged or human review, and produces operational outputs, tests, and documentation.

**Architecture:** Keep the pipeline split into input/schema, deterministic guardrails, HTTP classifier, and orchestration/reporting modules. The classifier is an OpenAI-compatible JSON HTTP adapter configured by environment variables; an offline deterministic adapter and failure simulation make the project runnable and testable without credentials. The pipeline gathers per-ticket results concurrently, then writes outputs once so counts cannot be lost through partial append failures.

**Tech Stack:** Python 3.11+, asyncio, Pydantic, httpx, python-dotenv, pytest, standard library.

**Spec:** `docs/superpowers/specs/2026-11-21-support-ticket-triage-design.md`

## Global Constraints

- Python 3.11+.
- Dependencies are limited to Pydantic, httpx, python-dotenv, and pytest; use the standard library for async orchestration, retry/backoff, timing, parsing, and reporting.
- Taxonomy is exactly `billing`, `technical_bug`, `account_access`, `security_privacy`, `feature_request`, `general_inquiry`.
- Priority is exactly `urgent`, `high`, `medium`, `low`.
- Per-attempt timeout is 8 seconds; transient failures receive at most 2 retries with exponential backoff and jitter.
- Confidence `< 0.80` escalates; urgent priority requires confidence `>= 0.90`.
- Risk keywords are `outage`, `down`, `production`, `breach`, `hacked`, `unauthorized`, `fraud`, `chargeback`, `data loss`, `lawsuit`, and `can't login`.
- Normalized body text shorter than 15 characters escalates without a model call.
- Every input row must appear in exactly one output file.

## Review Focus

- Malformed JSON/CSV rows: preserve them as human-review records instead of dropping or crashing; test in Task 1.
- HTML and excessive whitespace: normalize before context checks and prompts; test in Task 1.
- Retryable versus non-retryable model errors: retry boundedly, then fail closed; test in Task 3.
- Model response with extra prose or invalid enum/confidence: reject as invalid schema and escalate; test in Task 3.
- Duplicate or empty ticket IDs: preserve input order and account for each row; test in Task 4.

---

### Task 1: Project Setup, Schemas, and Input Loading

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/schemas.py`
- Create: `src/loader.py`
- Create: `tests/test_loader.py`
- Create: `tests/test_schemas.py`

**Interfaces:**
- Produces `Category`, `Priority`, `Ticket`, `TriageResult`, `ReviewRecord`, and `load_tickets(path: Path) -> list[Ticket | ReviewRecord]`.
- `Ticket` accepts `id`, `subject`, `body`, optional `created_at`, and preserves extra source fields in `metadata`.
- `ReviewRecord` represents malformed input with `escalation_reason="invalid_input"`.

- [x] **Step 1: Write failing schema tests**

Test enum acceptance/rejection, confidence bounds, required reasoning, and preservation of ticket IDs.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schemas.py -q`
Expected: import failures because `src.schemas` does not exist.

- [x] **Step 3: Implement strict Pydantic models**

Use string enums, `Field(ge=0.0, le=1.0)`, non-empty IDs, and a bounded/trimmed reasoning string. Keep output serialization JSON-compatible.

- [x] **Step 4: Run schema tests**

Run: `pytest tests/test_schemas.py -q`
Expected: PASS.

- [x] **Step 5: Write failing loader tests**

Cover JSON list input, CSV input, whitespace/HTML normalization, missing fields, malformed JSON rows, and empty rows becoming review records.

- [x] **Step 6: Implement `load_tickets` and normalization**

Detect `.json` and `.csv`; normalize `<br>`/tags and whitespace with standard-library regex/HTML utilities; convert row-level validation errors into `ReviewRecord` entries without aborting other rows.

- [x] **Step 7: Run loader tests**

Run: `pytest tests/test_loader.py -q`
Expected: PASS.

- [x] **Step 8: Commit**

```bash
git add requirements.txt .env.example src tests
git commit -m "feat: add ticket schemas and input loader\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 2: Deterministic Guardrails

**Files:**
- Create: `src/guardrails.py`
- Create: `tests/test_guardrails.py`

**Interfaces:**
- Produces `normalize_text(value: str) -> str`, `has_urgent_keyword(text: str) -> bool`, and `evaluate_guardrails(ticket: Ticket, result: TriageResult) -> str | None`.
- Return values are exact escalation reasons: `insufficient_context`, `low_confidence`, `urgent_keyword_mismatch`, `urgent_low_confidence`, or `None`.

- [x] **Step 1: Write failing guardrail tests**

Test body `< 15` characters, confidence `0.79`, risky text with medium/low priority, risky text with high/urgent priority, urgent confidence `0.89`, and a clean high-confidence ticket.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_guardrails.py -q`
Expected: import/function failures.

- [x] **Step 3: Implement guardrail functions**

Apply checks in this order: insufficient context, low confidence, urgent keyword mismatch, urgent low confidence. Match keywords case-insensitively as words/phrases after normalization.

- [x] **Step 4: Run guardrail tests**

Run: `pytest tests/test_guardrails.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/guardrails.py tests/test_guardrails.py
git commit -m "feat: add deterministic triage guardrails\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 3: Async Classifier with Retries and Fail-Safe Errors

**Files:**
- Create: `src/classifier.py`
- Create: `tests/test_classifier.py`

**Interfaces:**
- Produces `ClassifierConfig` and `AsyncClassifier.classify(ticket: Ticket) -> TriageResult`.
- Constructor accepts `httpx.AsyncClient`, `ClassifierConfig`, optional `random.Random`, and optional `failure_rate`.
- Raises a typed `ClassificationError` only internally; the public pipeline-facing method returns a valid `TriageResult` or a `ModelFailure` result carrying an escalation reason.

- [x] **Step 1: Write failing classifier tests**

Use `httpx.MockTransport` to test a valid JSON response, retryable 429 then success, timeout/failure after retries, invalid JSON/schema, and `failure_rate=1.0`. Assert no exception escapes and failures carry `model_unavailable` or `invalid_schema`.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_classifier.py -q`
Expected: import failures.

- [x] **Step 3: Implement bounded async classification**

Send a concise system prompt and ticket payload to the configured endpoint with JSON response mode. Wrap each attempt in `asyncio.timeout(8)`, retry only timeout/network/429/5xx failures up to two times, sleep with exponential backoff plus small random jitter, and parse through Pydantic. Convert terminal errors to a failure result rather than raising.

- [x] **Step 4: Run classifier tests**

Run: `pytest tests/test_classifier.py -q`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add src/classifier.py tests/test_classifier.py
git commit -m "feat: add resilient async classifier\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 4: Pipeline, Report, CLI, and End-to-End Invariant

**Files:**
- Create: `src/pipeline.py`
- Create: `main.py`
- Create: `tests/test_pipeline.py`
- Create: `data/tickets.json`
- Create: `output/.gitkeep`

**Interfaces:**
- Produces `PipelineConfig`, `run_pipeline(input_path: Path, output_dir: Path, classifier: AsyncClassifier, concurrency: int = 10) -> PipelineResult`, and `render_report(result: PipelineResult) -> str`.
- `PipelineResult` includes ordered `triaged`, `human_review`, per-ticket latencies, total runtime, and report text.
- CLI supports `--input`, `--output-dir`, `--concurrency`, `--simulate-failures RATE`, `--offline`, and `--timeout` (default 8.0).

- [x] **Step 1: Write failing pipeline tests**

Run with a fake classifier over valid, low-confidence, urgent-risk, short-body, and failed-model tickets. Assert every input appears once, order is stable, reasons are retained, concurrency is bounded, three output files are written, and report includes totals, percentages, p50/p95, category/priority tables, review reasons, and 3–5 samples.

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_pipeline.py -q`
Expected: import/function failures.

- [x] **Step 3: Implement bounded orchestration**

Create one task per ticket, use an `asyncio.Semaphore(concurrency)` around classifier calls, bypass the classifier for invalid/insufficient input, apply guardrails to successful model results, convert all exceptions to review records, and sort gathered results back to input order before partitioning.

- [x] **Step 4: Implement report and atomic output writes**

Write JSON files via temporary files followed by `os.replace`; calculate percentages against total input, p50/p95 with standard-library sorting, category/priority counts, reason counts, and escaped Markdown samples. Ensure missing reason categories render as zero.

- [x] **Step 5: Implement CLI and offline mode**

Load `.env` when present, select the HTTP classifier by default when `LLM_API_KEY` is configured, and use a deterministic local classifier with `--offline`; create a small 300-ticket sample input suitable for a credential-free smoke run.

- [x] **Step 6: Run pipeline tests and smoke test**

Run: `pytest tests/test_pipeline.py -q`
Expected: PASS.

Run: `python main.py --offline --input data/tickets.json --output-dir /tmp/ticket-triage-output`
Expected: exit 0, report printed, and output counts sum to 300.

- [x] **Step 7: Commit**

```bash
git add src/pipeline.py main.py tests/test_pipeline.py data/tickets.json output/.gitkeep
git commit -m "feat: add triage pipeline and operational report\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>"
```

### Task 5: Documentation, Packaging Checks, and Full Verification

**Files:**
- Create: `README.md`
- Modify: `tests/test_pipeline.py` if needed for final invariant coverage

- [x] **Step 1: Write README**

Document installation, `.env` configuration, online and offline commands, input shape, output shape, guardrail thresholds, retry/timeout behavior, chaos simulation, architecture, sample output, and the six-point 50,000-ticket/day design note.

- [x] **Step 2: Run the full test suite**

Run: `pytest -q`
Expected: all tests pass.

- [x] **Step 3: Run compile and smoke checks**

Run: `python -m compileall -q src main.py`
Expected: exit 0.

Run: `python main.py --offline --simulate-failures 0.1 --input data/tickets.json --output-dir /tmp/ticket-triage-chaos`
Expected: exit 0, zero dropped tickets, and some review records caused by simulated failures.

- [x] **Step 4: Inspect generated output invariants**

Run a short Python assertion against the smoke outputs: `len(triaged) + len(human_review) == 300`, IDs/counts match input rows, and every review record has `escalation_reason`.

- [x] **Step 5: Commit**

```bash
git add README.md tests
git commit -m "docs: document ticket triage setup and scaling\n\nCo-Authored-By: Claude Code <noreply@anthropic.com>"
```
