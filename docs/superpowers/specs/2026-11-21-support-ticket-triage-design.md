# Support Ticket Triage Design

## Intent

Build a greenfield Python 3.11+ service that processes a 300-ticket JSON or CSV input, classifies tickets asynchronously through a structured-output LLM, applies deterministic safety guardrails, routes every ticket to either automatic triage or human review, and emits operational output files and a report.

## Goals

- Validate and normalize input rows without dropping malformed tickets.
- Use strict Pydantic models for ticket data and model output.
- Process eligible tickets concurrently with a bounded semaphore.
- Enforce an 8-second per-attempt timeout and up to 2 retries with exponential backoff and jitter.
- Fail closed: model failures, invalid structured output, ambiguity, low confidence, and risky priority mismatches go to human review.
- Guarantee `len(triaged) + len(human_review) == len(input_rows)`.
- Write `output/triaged.json`, `output/human_review.json`, and `output/report.md`, and print a concise summary.
- Include a `--simulate-failures RATE` flag and focused pytest coverage.
- Document quickstart, architecture, thresholds, sample output, and a 50,000-ticket/day design note.

## Non-goals

- Production queue infrastructure, persistent resume storage, provider-specific SDK abstractions, or deployment configuration.
- Automatic human-review resolution.
- A dashboard beyond the generated Markdown report and CLI summary.

## Constraints and decisions

- Language: Python 3.11+.
- Dependencies: Pydantic, httpx, python-dotenv, pytest; use the standard library for asyncio, retries, timing, parsing, and reporting.
- Provider-neutral LLM adapter using an OpenAI-compatible JSON HTTP endpoint configured through `LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL`; no API key is required when `--offline` is used for local deterministic execution.
- Taxonomy: `billing`, `technical_bug`, `account_access`, `security_privacy`, `feature_request`, `general_inquiry`.
- Priorities: `urgent`, `high`, `medium`, `low`.
- Confidence gate: `< 0.80` escalates.
- Urgent confidence gate: `urgent` with `< 0.90` escalates.
- Risk keywords include `outage`, `down`, `production`, `breach`, `hacked`, `unauthorized`, `fraud`, `chargeback`, `data loss`, `lawsuit`, and `can't login`; risky text with model priority `medium` or `low` escalates.
- Body text shorter than 15 normalized characters escalates before any model call.
- Each output record retains the original/normalized ticket data, model result when available, latency, and escalation reason when applicable.

## Data flow

1. Load JSON list or CSV rows.
2. Convert each row into a valid ticket record; malformed rows become synthetic review records rather than crashing or disappearing.
3. Normalize subject/body whitespace and basic HTML tags.
4. Route insufficient context directly to human review.
5. Call the LLM under a semaphore, timeout, retry policy, and optional failure simulation.
6. Validate the response with Pydantic.
7. Apply confidence, urgent keyword, and urgent-confidence guardrails in deterministic order.
8. Write the two JSON outputs and aggregate the report.

## Outputs

- `output/triaged.json`: high-confidence records passing all gates.
- `output/human_review.json`: records with `escalation_reason` and any model draft/reasoning available.
- `output/report.md`: execution totals, percentages, runtime, average/p95 latency, category and priority breakdowns, escalation counts, and 3–5 escaped-ticket samples.

## Testing

Tests cover schema bounds, input normalization/validation, insufficient context, low confidence, risky keyword mismatch, urgent confidence, model failure fallback, failure simulation, and the invariant that all inputs are accounted for.

## Scaling note

README documents queue-based ingestion, tiered deterministic/model routing and caching, retries/circuit breaking/failover, quality monitoring, golden datasets and shadow audits, and cost/latency SLOs for 50,000 tickets/day.
