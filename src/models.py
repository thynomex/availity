from enum import Enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UsernameStatus(str, Enum):
    PENDING = "pending"
    CHECKING = "checking"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    INVALID = "invalid"
    RATE_LIMITED = "rate_limited"
    ERROR = "error"
    SKIPPED_BY_USER_LIMIT = "skipped_by_user_limit"


class CharMode(str, Enum):
    LETTERS = "letters"
    NUMBERS = "numbers"
    ALPHANUMERIC = "alphanumeric"
    CUSTOM = "custom"
    DICTIONARY = "dictionary"


class ValidationResult(BaseModel):
    valid: bool
    reason: Optional[str] = None


class AvailabilityResult(BaseModel):
    username: str
    status: UsernameStatus
    checked_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    provider_metadata: Optional[dict] = None


class Candidate(BaseModel):
    username: str
    status: UsernameStatus = UsernameStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    checked_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int = 0


class RunRecord(BaseModel):
    run_id: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_candidates: int = 0
    checked: int = 0
    available: int = 0
    errors: int = 0
