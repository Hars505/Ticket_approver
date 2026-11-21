# Support Ticket Triage Backend

A high-throughput, provider-neutral, fail-safe asynchronous Python service that classifies customer support tickets, enforces deterministic safety guardrails, routes records to either automated triage or human review, and produces operational audit outputs and reports.

---

## Architecture Overview

```
                      +-----------------------------+
                      | Input File (.json / .csv)   |
                      +--------------+--------------+
                                     |
                                     v
                      +-----------------------------+
                      |     Input Loader & Clean     |
                      |  - HTML tag removal         |
                      |  - Whitespace normalization |
                      |  - Row-level validation     |
                      +--------------+--------------+
                                     |
                     [Malformed row or body < 15]
                     /                           \
                    v                             v
+-------------------------------+      +---------------------------------+
| Human Review:                 |      | Async LLM Classifier            |
| "invalid_input" or            |      | - Bounded Semaphore (concurrency)|
| "insufficient_context"        |      | - 8s timeout per attempt        |
+-------------------------------+      | - Max 2 retries (429/5xx/net)   |
                                       | - Exponential backoff + jitter  |
                                       +----------------+----------------+
                                                        |
                                              [Terminal Failure / Bad JSON]
                                              /                          \
                                             v                            v
                          +------------------------+           +----------------------+
                          | Human Review:          |           | TriageResult Schema  |
                          | "model_unavailable" or |           +----------+-----------+
                          | "invalid_schema"       |                      |
                          +------------------------+                      v
                                                       +----------------------+
                                                       | Deterministic        |
                                                       | Guardrails Gate      |
                                                       +----------+-----------+
                                                                  |
                                       +--------------------------+--------------------------+
                                       |                                                     |
                         [Passes All Guardrails]                            [Triggered Guardrail Violation]
                                       |                                                     |
                                       v                                                     v
                         +---------------------------+                         +----------------------------+
                         | `output/triaged.json`     |                         | `output/human_review.json` |
                         | - Validated Ticket        |                         | - "low_confidence"         |
                         | - Category & Priority     |                         | - "urgent_keyword_mismatch"|
                         | - Confidence (>= 0.80)    |                         | - "urgent_low_confidence"  |
                         | - Reasoning & Latency     |                         | - Preserved model draft    |
                         +---------------------------+                         +----------------------------+
```

---

## Key Features & Invariants

1. **Strict Pydantic Validation**:
   - Fixed 6-category taxonomy: `billing`, `technical_bug`, `account_access`, `security_privacy`, `feature_request`, `general_inquiry`.
   - Fixed 4 priorities: `urgent`, `high`, `medium`, `low`.
   - Bounded confidence `[0.0, 1.0]`.
2. **Zero-Drop Guarantee**:
   - Invariant: `len(triaged) + len(human_review) == len(input_rows)`.
   - Every input row appears in exactly one output destination.
3. **Deterministic Safety Guardrails**:
   - **Insufficient Context**: Normalized body length `< 15` characters escalates immediately without model calls.
   - **Confidence Floor**: Model confidence `< 0.80` escalates to `low_confidence`.
   - **Urgent Keyword Mismatch**: Presence of risk keywords (`outage`, `down`, `production`, `breach`, `hacked`, `unauthorized`, `fraud`, `chargeback`, `data loss`, `lawsuit`, `can't login`) with model priority `medium` or `low` escalates to `urgent_keyword_mismatch`.
   - **Urgent Confidence Gate**: Priority `urgent` requires confidence `>= 0.90`; otherwise escalates to `urgent_low_confidence`.
4. **Resilient HTTP Classifier & Chaos Simulation**:
   - Provider-neutral OpenAI-compatible JSON endpoint.
   - 8-second timeout per attempt.
   - Up to 2 retries on 429 rate limits, 5xx server errors, or transient network timeouts with exponential backoff and jitter.
   - Built-in `--simulate-failures RATE` to inject chaos faults.
   - Offline mode (`--offline`) allows full local execution and testing without credentials.
5. **Atomic Outputs**:
   - Writes `output/triaged.json`, `output/human_review.json`, and `output/report.md` atomically using temporary files and filesystem replace operations.

---

## Quickstart

### Prerequisites
- Python 3.11+
- Virtual environment (recommended)

### Installation
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Environment Configuration
Copy `.env.example` to `.env` to configure an OpenAI-compatible remote endpoint (optional for online mode):
```bash
cp .env.example .env
```
Edit `.env`:
```env
LLM_API_KEY=your-api-key-here
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

---

## Running the Pipeline

### 1. Offline Mode (Credential-Free)
Run against the bundled 300-ticket dataset using deterministic heuristic rules:
```bash
python main.py --offline --input data/tickets.json --output-dir output
```

### 2. Online Mode
Run with remote LLM completion:
```bash
python main.py --input data/tickets.json --output-dir output --concurrency 10
```

### 3. Chaos Simulation
Simulate a 10% rate of transient model failures to verify fail-closed escalation routing:
```bash
python main.py --offline --simulate-failures 0.10 --input data/tickets.json --output-dir output
```

### CLI Options
| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--input` | Path | `data/tickets.json` | Path to JSON or CSV input file |
| `--output-dir` | Path | `output` | Directory where outputs are written |
| `--concurrency` | Int | `10` | Max concurrent worker tasks |
| `--simulate-failures` | Float | `0.0` | Probability (0.0 - 1.0) of simulated model failures |
| `--offline` | Flag | `False` | Run using local deterministic classifier |
| `--timeout` | Float | `8.0` | Per-request timeout in seconds |

---

## Input & Output Formats

### Input Formats Supported
- **JSON List**: Array of ticket objects containing `id`, `subject`, `body`, optional `created_at`, and arbitrary metadata fields.
- **CSV**: Columns matching `id`, `subject`, `body`, `created_at` (extra columns preserved in metadata).

### Output Artifacts
- **`output/triaged.json`**:
  ```json
  [
    {
      "ticket": {
        "id": "TCK-0001",
        "subject": "Invoice request for renewal",
        "body": "Please provide the official invoice and VAT receipt for our annual enterprise subscription renewal. (Ref: ticket-1)",
        "created_at": "2026-11-21T00:00:00Z",
        "metadata": { "customer_tier": "standard", "index": 0 }
      },
      "triage": {
        "category": "billing",
        "priority": "low",
        "confidence": 0.88,
        "reasoning": "Offline deterministic rule matched 'billing' with priority 'low'."
      },
      "latency_ms": 0.12
    }
  ]
  ```

- **`output/human_review.json`**:
  ```json
  [
    {
      "ticket_id": "TCK-0291",
      "ticket": {
        "id": "TCK-0291",
        "subject": "Help",
        "body": "Help me",
        "created_at": "2026-11-21T12:00:00Z",
        "metadata": { "short_context": true }
      },
      "raw_data": { ... },
      "model_draft": null,
      "escalation_reason": "insufficient_context",
      "latency_ms": 0.0,
      "metadata": { "short_context": true }
    }
  ]
  ```

- **`output/report.md`**: Markdown operational report with summary metrics, average/p50/p95 latencies, taxonomy and priority breakdowns, escalation distributions, and escaped sample tickets.

---

## Testing

Run the automated test suite covering schemas, input loading, guardrails, async classifier retries, and pipeline invariants:
```bash
pytest -v
```

---

## Scaling to 50,000 Tickets / Day: Architectural Roadmap

To scale this service from batch runs to a continuous 50,000 ticket/day production workload (~35 tickets/min average, ~150-300 tickets/min peak), implement the following six architectural enhancements:

1. **Distributed Queue Ingestion**:
   - Replace filesystem batch loading with partitioned message queues (Apache Kafka, AWS SQS, or Redis Streams).
   - Ingestion workers validate and normalize incoming webhooks/events and publish to an `incoming-tickets` topic, decoupling upstream webhook producers from processing latency spikes.

2. **Tiered Deterministic Routing & Semantic Caching**:
   - **Tier 0 Deterministic Filter**: High-precision regex rules bypass the LLM for canonical transactional requests (e.g., standard "resend invoice" or "unsubscribe"), triaging up to 25-35% of volume in < 2ms.
   - **Semantic Vector Cache**: Exact-match hashing and embedding similarity cache (e.g. Redis + Qdrant) over normalized query texts to reuse triages for identical inquiries without LLM token cost.

3. **Multi-Provider Failover & Circuit Breaking**:
   - Integrate circuit breakers (e.g. sliding window failure rates).
   - If primary provider (e.g. OpenAI) returns sustained 5xx/429 errors, automatically divert traffic to secondary providers (e.g. Anthropic, Google Gemini, or a self-hosted vLLM cluster).

4. **Continuous Quality Monitoring & Drift Detection**:
   - Stream triage events to an observability sink (Prometheus / OpenTelemetry / ClickHouse).
   - Set automated alerting on:
     - Escalation rate anomalies (e.g., human review rate spiking above historical baseline).
     - Confidence distribution drift (Kolmogorov-Smirnov test over rolling 1-hour windows).
     - Category distribution shifts signaling emerging incidents.

5. **Golden Datasets & Continuous Shadow Audits**:
   - Maintain a curated "Golden Dataset" of 2,000 human-annotated edge cases run against CI/CD pipelines on every prompt or model upgrade.
   - Implement shadow sampling: randomly route 2% of automated triages to secondary human review to continuously compute precision, recall, and false-positive rates.

6. **Cost & Latency SLO Management**:
   - Target Latency SLO: p95 `< 1200ms`, p99 `< 2500ms`.
   - Dynamic Model Cascades: Route standard queries to cost-efficient models (e.g., `gpt-4o-mini`, `gemini-1.5-flash`), reserving larger reasoning models only for high-entropy tickets that fail confidence thresholds on the first pass.
