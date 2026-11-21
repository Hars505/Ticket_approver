from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    BILLING = "billing"
    TECHNICAL_BUG = "technical_bug"
    ACCOUNT_ACCESS = "account_access"
    SECURITY_PRIVACY = "security_privacy"
    FEATURE_REQUEST = "feature_request"
    GENERAL_INQUIRY = "general_inquiry"


class Priority(str, Enum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Ticket(BaseModel):
    id: str
    subject: str = ""
    body: str
    created_at: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id_not_empty(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Ticket ID must not be empty.")
        return trimmed


class TriageResult(BaseModel):
    category: Category
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str

    @field_validator("reasoning")
    @classmethod
    def validate_reasoning_not_empty(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Reasoning must not be empty.")
        return trimmed


class ReviewRecord(BaseModel):
    ticket_id: Optional[str] = None
    ticket: Optional[Ticket] = None
    raw_data: Any = None
    model_draft: Optional[TriageResult] = None
    escalation_reason: str
    latency_ms: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)

