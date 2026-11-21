import asyncio
import json
import random
from typing import Optional
import httpx
from pydantic import BaseModel, Field, ValidationError

from src.guardrails import has_urgent_keyword
from src.schemas import Category, Priority, Ticket, TriageResult


SYSTEM_PROMPT = """You are an automated support ticket classifier.
You must analyze the ticket subject and body and respond with a JSON object adhering to this schema:
{
  "category": "billing" | "technical_bug" | "account_access" | "security_privacy" | "feature_request" | "general_inquiry",
  "priority": "urgent" | "high" | "medium" | "low",
  "confidence": <float between 0.0 and 1.0>,
  "reasoning": "<concise explanation>"
}
Do not include any Markdown fences or text outside the JSON object.
"""


class ClassifierConfig(BaseModel):
    api_key: str = ""
    base_url: str = "https://api.openai.com/v1"
    model: str = "gemini-flash-lite-latest"
    timeout_seconds: float = 20.0
    max_retries: int = 2
    backoff_base_seconds: float = 0.5


class ModelFailure(BaseModel):
    escalation_reason: str = "model_unavailable"  # "model_unavailable" or "invalid_schema"
    error_message: str
    raw_response: Optional[str] = None


class ClassificationError(Exception):
    """Internal typed exception for classification attempts."""
    def __init__(self, message: str, is_retryable: bool = False, status_code: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.is_retryable = is_retryable
        self.status_code = status_code


class AsyncClassifier:
    """Async classifier that sends tickets to an OpenAI-compatible endpoint with bounded retries."""

    def __init__(
        self,
        client: httpx.AsyncClient,
        config: Optional[ClassifierConfig] = None,
        rng: Optional[random.Random] = None,
        failure_rate: float = 0.0,
        fallback_on_rate_limit: bool = False,
    ):
        self.client = client
        self.config = config or ClassifierConfig()
        self.rng = rng or random.Random()
        self.failure_rate = max(0.0, min(1.0, failure_rate))
        self.fallback_on_rate_limit = fallback_on_rate_limit

    async def _attempt_request(self, ticket: Ticket) -> str:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        user_content = json.dumps(
            {
                "id": ticket.id,
                "subject": ticket.subject,
                "body": ticket.body,
            }
        )
        payload = {
            "model": self.config.model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0.0,
        }

        try:
            async with asyncio.timeout(self.config.timeout_seconds):
                response = await self.client.post(url, headers=headers, json=payload)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ClassificationError(f"Request timed out: {exc}", is_retryable=True) from exc
        except httpx.NetworkError as exc:
            raise ClassificationError(f"Network error: {exc}", is_retryable=True) from exc

        if response.status_code == 429:
            raise ClassificationError("Rate limit exceeded (429)", is_retryable=True, status_code=429)
        elif 500 <= response.status_code < 600:
            raise ClassificationError(
                f"Server error ({response.status_code}): {response.text}",
                is_retryable=True,
                status_code=response.status_code,
            )
        elif response.status_code != 200:
            raise ClassificationError(
                f"HTTP {response.status_code}: {response.text}",
                is_retryable=False,
                status_code=response.status_code,
            )

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return content
        except Exception as exc:
            raise ClassificationError(
                f"Malformed response payload structure: {exc}",
                is_retryable=False,
            ) from exc

    async def classify(self, ticket: Ticket) -> TriageResult | ModelFailure:
        """Classify a ticket, returning a valid TriageResult or a fail-safe ModelFailure."""
        if self.failure_rate > 0.0 and self.rng.random() < self.failure_rate:
            return ModelFailure(
                escalation_reason="model_unavailable",
                error_message="Simulated chaos failure",
            )

        max_attempts = 1 + self.config.max_retries
        last_error_message = ""

        for attempt in range(max_attempts):
            try:
                raw_content = await self._attempt_request(ticket)
                # Parse JSON and validate against schema
                try:
                    parsed = json.loads(raw_content)
                    if not isinstance(parsed, dict):
                        return ModelFailure(
                            escalation_reason="invalid_schema",
                            error_message="Model response is not a JSON dictionary",
                            raw_response=raw_content,
                        )
                    return TriageResult.model_validate(parsed)
                except (json.JSONDecodeError, ValidationError) as parse_err:
                    return ModelFailure(
                        escalation_reason="invalid_schema",
                        error_message=f"Schema validation failed: {parse_err}",
                        raw_response=raw_content,
                    )
            except ClassificationError as exc:
                last_error_message = exc.message
                if not exc.is_retryable or attempt >= self.config.max_retries:
                    break
                # Exponential backoff + small jitter
                sleep_s = (self.config.backoff_base_seconds * (2 ** attempt)) + self.rng.uniform(0.01, 0.05)
                await asyncio.sleep(sleep_s)
            except Exception as exc:
                last_error_message = f"Unexpected error: {exc}"
                break

        if self.fallback_on_rate_limit and "429" in last_error_message and self.failure_rate == 0.0:
            fallback_clf = OfflineClassifier(rng=self.rng)
            fb_res = await fallback_clf.classify(ticket)
            if isinstance(fb_res, TriageResult):
                fb_res.reasoning += " [Provider 15 RPM quota limit reached; resolved via local fallback]"
                return fb_res

        return ModelFailure(
            escalation_reason="model_unavailable",
            error_message=last_error_message or "Model call failed",
        )


class OfflineClassifier(AsyncClassifier):
    """Deterministic local classifier for credential-free execution and testing."""

    def __init__(
        self,
        rng: Optional[random.Random] = None,
        failure_rate: float = 0.0,
    ):
        super().__init__(
            client=None,  # type: ignore[arg-type]
            config=ClassifierConfig(),
            rng=rng,
            failure_rate=failure_rate,
        )

    async def classify(self, ticket: Ticket) -> TriageResult | ModelFailure:
        if self.failure_rate > 0.0 and self.rng.random() < self.failure_rate:
            return ModelFailure(
                escalation_reason="model_unavailable",
                error_message="Simulated chaos failure",
            )

        # Deterministic heuristic mapping
        text = f"{ticket.subject} {ticket.body}".lower()

        # Check category
        if any(w in text for w in ["invoice", "bill", "refund", "charge", "payment", "subscription", "price"]):
            cat = Category.BILLING
        elif any(w in text for w in ["password", "login", "reset", "2fa", "mfa", "locked", "sso", "authenticator"]):
            cat = Category.ACCOUNT_ACCESS
        elif any(w in text for w in ["security", "breach", "vulnerability", "privacy", "gdpr", "leak", "unauthorized"]):
            cat = Category.SECURITY_PRIVACY
        elif any(w in text for w in ["feature", "request", "suggest", "would like", "enhancement", "roadmap"]):
            cat = Category.FEATURE_REQUEST
        elif any(w in text for w in ["error", "bug", "crash", "broken", "exception", "500", "fails", "glitch"]):
            cat = Category.TECHNICAL_BUG
        else:
            cat = Category.GENERAL_INQUIRY

        # Check priority
        if has_urgent_keyword(text):
            prio = Priority.URGENT
            conf = 0.95
        elif any(w in text for w in ["urgent", "asap", "critical", "blocker", "important"]):
            prio = Priority.HIGH
            conf = 0.91
        elif any(w in text for w in ["soon", "moderate", "minor"]):
            prio = Priority.MEDIUM
            conf = 0.86
        else:
            prio = Priority.LOW
            conf = 0.88

        # Generate realistic context-aware reasoning
        subj_clean = ticket.subject.strip() if ticket.subject else "support request"
        if cat == Category.BILLING:
            reason = f"Customer request regarding subscription billing, payment reconciliation, or invoices: '{subj_clean}'."
        elif cat == Category.TECHNICAL_BUG:
            reason = f"Technical report describes application errors, unexpected system crashes, or defective behaviors: '{subj_clean}'."
        elif cat == Category.ACCOUNT_ACCESS:
            reason = f"Account access or identity recovery issue preventing user sign-in: '{subj_clean}'."
        elif cat == Category.SECURITY_PRIVACY:
            reason = f"Security, privacy, or compliance notification requiring prioritized verification: '{subj_clean}'."
        elif cat == Category.FEATURE_REQUEST:
            reason = f"Customer is proposing workflow enhancement or platform capability request: '{subj_clean}'."
        else:
            reason = f"Customer inquiry regarding platform documentation, policies, or service terms: '{subj_clean}'."

        if prio == Priority.URGENT:
            reason += " Escalated to urgent priority due to critical operational risk terminology."

        return TriageResult(
            category=cat,
            priority=prio,
            confidence=conf,
            reasoning=reason,
        )

