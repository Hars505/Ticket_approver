# Queuewatch — Automated Support Ticket Triage & Audit Console

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-18+-61DAFB.svg)](https://react.dev)
[![Vite](https://img.shields.io/badge/Vite-6+-646CFF.svg)](https://vitejs.dev)
[![Tests Passing](https://img.shields.io/badge/tests-28%20passed-brightgreen.svg)]()

A high-throughput, provider-neutral, fail-safe support ticket triage platform. Combines structured LLM intelligence (**Google Gemini** or **OpenAI-compatible** endpoints) with **deterministic safety guardrails**, an automated **human review queue**, and an interactive **React operations console**.

---

## Table of Contents

- [System Architecture](#system-architecture)
- [Core Invariants & Safety Guardrails](#core-invariants--safety-guardrails)
- [Quickstart](#quickstart)
- [Application Views & Frontend Console](#application-views--frontend-console)
- [API Reference](#api-reference)
- [CLI Reference](#cli-reference)
- [LLM Provider Configuration](#llm-provider-configuration)
- [Testing](#testing)
- [Production Scaling: 50,000 Tickets/Day](#production-scaling-50000-ticketsday)

---

## System Architecture

```
                                  +-----------------------------+
                                  | Input Queue (.json / .csv)  |
                                  +--------------+--------------+
                                                 |
                                                 v
                                  +-----------------------------+
                                  |     Input Loader & Clean     |
                                  |  - HTML tag removal         |
                                  |  - Whitespace normalization |
                                  |  - Zero-drop row validation |
                                  +--------------+--------------+
                                                 |
                                [Malformed row or body < 15 chars]
                                /                                \
                               v                                  v
            +-------------------------------+   +---------------------------------+
            | Escalation:                   |   | Async LLM Classifier            |
            | "invalid_input" or            |   | - Bounded Semaphore concurrency |
            | "insufficient_context"        |   | - 20s timeout per attempt       |
            +---------------+---------------+   | - Max 2 retries (429/5xx/net)   |
                            |                   | - Exponential backoff + jitter  |
                            |                   +----------------+----------------+
                            |                                    |
                            |                          [429 Rate Limit / Error]
                            |                          /                       \
                            |                         v                         v
                            |           +-------------------------+  +----------------------+
                            |           | Rate Limit Fallback /   |  | Structured Output:   |
                            |           | "model_unavailable"    |  | TriageResult Schema  |
                            |           +------------+------------+  +----------+-----------+
                            |                        |                          |
                            |                        v                          v
                            |           +-----------------------------------------------+
                            |           |         Deterministic Guardrails Gate         |
                            |           |  1. Insufficient context check                |
                            |           |  2. Confidence floor (< 0.80)                 |
                            |           |  3. Urgent keyword mismatch check             |
                            |           |  4. Urgent low-confidence check (< 0.90)      |
                            |           +-----------------------+-----------------------+
                            |                                   |
                            |                +------------------+------------------+
                            |                |                                     |
                            |   [Passes All Guardrails]             [Triggered Violation]
                            |                |                                     |
                            v                v                                     v
            +------------------------------------+             +------------------------------------+
            |        `output/triaged.json`       |             |     `output/human_review.json`     |
            | - Validated Ticket Model           |             | - Exact Escalation Reason          |
            | - Category & Priority              |             | - Original Ticket Payload          |
            | - Confidence Score & Reasoning     |             | - Preserved AI Draft & Latency     |
            | - Execution Latency (ms)           |             | - Reviewer Actions Ready           |
            +------------------------------------+             +------------------------------------+
```

---

## Core Invariants & Safety Guardrails

1. **Zero-Drop Guarantee**:
   $$\text{len(triaged)} + \text{len(human\_review)} \equiv \text{len(input\_rows)}$$
   No ticket is ever dropped, lost, or silently ignored. Every input record is strictly accounted for in exactly one output queue.
2. **Deterministic Safety Guardrails**:
   - **Insufficient Context**: Any ticket with a normalized body under 15 characters escalates immediately to human review without wasting LLM tokens (`insufficient_context`).
   - **Confidence Floor**: Model confidence below `0.80` triggers escalation (`low_confidence`).
   - **Urgent Keyword Mismatch**: Presence of critical risk keywords (`outage`, `down`, `production`, `breach`, `hacked`, `unauthorized`, `fraud`, `chargeback`, `data loss`, `lawsuit`, `can't login`) classified by the model with `medium` or `low` priority triggers escalation (`urgent_keyword_mismatch`).
   - **Urgent Confidence Gate**: Urgent priority requires confidence $\ge 0.90$; otherwise escalates to `urgent_low_confidence`.
3. **Fixed Taxonomy & Priorities**:
   - **Categories (6)**: `billing`, `technical_bug`, `account_access`, `security_privacy`, `feature_request`, `general_inquiry`.
   - **Priorities (4)**: `urgent`, `high`, `medium`, `low`.
4. **Provider-Neutral Fail-Safe Engine**:
   - Automatically handles Google Gemini API 15 RPM free-tier limits by auto-fallback to the rich local engine, ensuring complete batch processing without service interruption.

---

## Quickstart

### Prerequisites
- Python 3.11+
- Node.js 18+ (optional, only needed for modifying frontend source)

### 1. Installation

```bash
git clone <repo-url>
cd Tech

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Launch the Application

Start the combined backend and compiled frontend console in a single command:

```bash
python main.py --serve --port 8000
```

Open your browser at **[http://localhost:8000](http://localhost:8000)**.

---

## Application Views & Frontend Console

The web console (`frontend/`) is built with React, Vite, Framer Motion, and Lucide:

### 1. Overview & Report (`/overview`)
- **Real-Time KPIs**: Total processed, auto-triaged rate, human review count, and average / p95 model latency.
- **Classification Taxonomy**: Interactive category breakdown progress bars.
- **Priority Distribution**: Visual stacked bar showing risk ratios (`urgent`, `high`, `medium`, `low`).
- **Escalation Reason Counter**: Itemized breakdown of held tickets.
- **Action Strip**: Instant batch upload for `.json` and `.csv` files; one-click Markdown report export.

### 2. Human Review Queue (`/review`)
- **Queue Filtering**: Filter by reason (`Urgent mismatch`, `Low confidence`, `Short body`, `Model error`).
- **Ticket Inspector**: Displays original customer message with **highlighted risk terms**.
- **AI Draft Box**: Inspects model classification, confidence, and reasoning.
- **Human Decision Block**: Dropdowns to adjust Category and Priority.
- **Keyboard Shortcut**: Press <kbd>Enter</kbd> to approve the ticket and instantly advance to the next item.
- **Export Queue**: Downloads `human_review_queue.json` directly.

### 3. Auto-Triaged Audit View (`/triaged`)
- **Search & Filters**: Real-time search across ticket IDs, subjects, and bodies with category/priority filters.
- **Expandable Rows**: Inspect customer message and full AI reasoning.
- **"Flag as Wrong"**: One-click action to redirect misclassified tickets into the human review queue.
- **Export Triaged**: Downloads `triaged_tickets.json` with full classification metadata.

### 4. Settings & Guardrail Tuning (`/settings`)
- **Confidence Threshold Slider**: Adjust cutoff score from `0.50` to `0.95`.
- **Failure Simulation (Chaos)**: Inject synthetic error rates (`0%` to `20%`) to test fail-safe routing.
- **Urgent Keyword Editor**: Add or remove monitored risk words dynamically.
- **Engine Switcher**: Switch between `⚡ Local Engine` and `✨ Gemini Cloud AI` from the topbar or settings.

---

## API Reference

The backend provides a REST API via FastAPI at `http://localhost:8000`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/health` | Health check, active model, and provider configuration status. |
| `GET` | `/api/overview` | Aggregated metrics, category counts, priority distribution, and latency stats. |
| `GET` | `/api/tickets/triaged` | Paginated auto-triaged tickets (`search`, `category`, `priority`, `limit`, `offset`). |
| `GET` | `/api/tickets/review` | Paginated review queue tickets (`search`, `filter`, `limit`, `offset`). |
| `POST` | `/api/tickets/{id}/approve` | Reviewer decision: approves a review ticket and moves it into `triaged.json`. |
| `POST` | `/api/tickets/{id}/flag` | Audit action: flags a triaged ticket and routes it back to `human_review.json`. |
| `POST` | `/api/triage/run` | Triggers a full pipeline execution (`threshold`, `simulate_failures`, `offline`, `concurrency`). |
| `POST` | `/api/triage/single` | Live real-time classification for a single ticket body & subject. |
| `POST` | `/api/upload` | Uploads a `.json` or `.csv` ticket file and triggers immediate triage. |
| `GET` | `/api/report/download` | Downloads the operational Markdown report. |
| `GET` | `/api/settings` | Retrieves current threshold, chaos rate, and urgent keyword list. |
| `POST` | `/api/settings` | Updates runtime guardrail settings. |

---

## CLI Reference

`main.py` provides standalone batch execution and server orchestration:

```bash
# Start full-stack web console
python main.py --serve --port 8000

# Run batch triage offline (instant execution for 300 tickets)
python main.py --offline --input data/tickets.json --output-dir output

# Run batch triage online with remote LLM
python main.py --input data/tickets.json --output-dir output --concurrency 5

# Run chaos test with 10% injected failure rate
python main.py --offline --simulate-failures 0.10 --input data/tickets.json --output-dir output
```

### CLI Options

| Flag | Default | Description |
| :--- | :--- | :--- |
| `--serve` | `False` | Launch FastAPI web server and host frontend console |
| `--port` | `8000` | Port for the web server |
| `--input` | `data/tickets.json` | Path to JSON or CSV input file |
| `--output-dir` | `output` | Destination directory for output files |
| `--offline` | `False` | Use deterministic local engine instead of cloud API |
| `--simulate-failures` | `0.0` | Probability (0.0 to 1.0) of synthetic model failures |
| `--concurrency` | `10` | Maximum parallel async workers |
| `--timeout` | `20.0` | Per-request timeout in seconds |

---

## LLM Provider Configuration

Configure your credentials in [.env](file:///home/harshil/STUDY/Tech/.env) (copied from [.env.example](file:///home/harshil/STUDY/Tech/.env.example)):

### Option 1: Google Gemini (Recommended Cloud Provider)
```env
LLM_API_KEY=AIzaSy...your_gemini_api_key_here
LLM_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
LLM_MODEL=gemini-flash-lite-latest
```
*(Get a free key at [aistudio.google.com/apikey](https://aistudio.google.com/apikey))*

### Option 2: OpenAI
```env
LLM_API_KEY=sk-proj-...
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

### Option 3: Local Ollama (Zero Cost, 100% Private)
```env
LLM_API_KEY=ollama
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.2
```

---

## Testing

Run the full pytest suite covering schemas, normalizers, guardrails, async retry logic, pipeline invariants, and API endpoints:

```bash
pytest -v
```

```
tests/test_schemas.py      ....                                   [ 14%]
tests/test_loader.py       .....                                  [ 32%]
tests/test_guardrails.py   .......                                [ 57%]
tests/test_classifier.py   .....                                  [ 75%]
tests/test_pipeline.py     .                                      [ 78%]
tests/test_api.py          ......                                 [100%]
============================== 28 passed in 1.15s ==============================
```

---

## Production Scaling: 50,000 Tickets/Day

To transition from batch processing to continuous enterprise throughput (~35 tickets/min average, ~250 tickets/min peak), implement the following six architectural steps:

1. **Distributed Event Streaming**:
   - Transition input loading to Apache Kafka or AWS SQS with partitioned consumer worker pools. Decouple incoming webhook ingestion from classifier processing latency.
2. **Tier-0 Deterministic Routing & Semantic Caching**:
   - High-precision regex rules triage canonical requests (e.g. standard "invoice receipt" or "reset password") in `< 2ms`, handling 25–35% of volume with zero LLM token costs.
   - Exact-match hashing and embedding similarity caching (Redis + Qdrant) avoid re-classifying duplicate inquiries.
3. **Multi-Region Failover & Circuit Breaking**:
   - Implement sliding-window circuit breakers. If primary provider (e.g. Gemini) returns 429/5xx, divert traffic across secondary providers (OpenAI, Anthropic, or self-hosted vLLM).
4. **Automated Drift & Quality Monitoring**:
   - Stream triage metrics to Prometheus / OpenTelemetry. Alert on escalation rate spikes ($> 20\%$) or category distribution drift indicating emerging platform incidents.
5. **Golden Datasets & Shadow QA**:
   - Continuous CI validation against a 2,000-ticket curated edge-case dataset.
   - Automatically route a 2% random sample of auto-triaged tickets to human QA to track false-positive rates.
6. **Latency SLO & Cascading Models**:
   - Target SLO: p95 $< 1200\text{ms}$, p99 $< 2500\text{ms}$.
   - Cascade small, fast models (`gemini-flash-lite`, `gpt-4o-mini`) for tier-1 classification, reserving larger reasoning models only for high-entropy tickets that fail initial confidence gates.
