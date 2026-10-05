"""Request/response models for mock interviews and their admin screens."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import Difficulty, InterviewStatus, ReportStatus
from app.modules.interviews.schemas import ReportResult


class InterviewTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    description: str
    duration_minutes: int
    question_count: int
    difficulty: Difficulty


class InterviewCreate(BaseModel):
    type_key: str = Field(max_length=30)
    difficulty: Difficulty | None = None
    job_id: uuid.UUID | None = None


class InterviewMessageOut(BaseModel):
    id: uuid.UUID
    seq: int
    role: Literal["interviewer", "candidate"]
    kind: str
    question_index: int | None
    content: str
    attachment: str | None
    interrupted: bool
    created_at: datetime


class InterviewState(BaseModel):
    """The live state the interview room renders (also sent over the WebSocket)."""

    id: uuid.UUID
    status: InterviewStatus
    type_key: str
    difficulty: Difficulty
    duration_minutes: int
    current_index: int
    total_questions: int
    current_kind: str | None  # coding | design | behavioral | technical
    followups_used: int
    max_followups: int
    hints_used: int
    started_at: datetime | None
    ends_at: datetime | None
    ended_at: datetime | None
    end_reason: str | None
    job_title: str | None
    company_name: str | None


class InterviewDetail(BaseModel):
    interview: InterviewState
    type_name: str
    messages: list[InterviewMessageOut]
    report_status: ReportStatus | None
    overall_score: int | None
    error: str | None


class InterviewSummary(BaseModel):
    id: uuid.UUID
    type_key: str
    type_name: str
    status: InterviewStatus
    difficulty: Difficulty
    job_title: str | None
    company_name: str | None
    created_at: datetime
    ended_at: datetime | None
    report_status: ReportStatus | None
    overall_score: int | None


class SocketTicket(BaseModel):
    ticket: str
    url: str  # ws(s)://.../ws/interviews/{id}; append ?ticket=
    expires_in: int


class ReportOut(BaseModel):
    status: ReportStatus
    overall_score: int | None
    result: ReportResult | None
    error: str | None
    generated_by: str | None
    interview: InterviewSummary


# --- admin ---

_KEY = re.compile(r"^[a-z][a-z0-9_]{1,39}$")


class RubricCriterion(BaseModel):
    key: str
    name: str = Field(min_length=1, max_length=60)
    description: str = Field(default="", max_length=300)
    weight: float = Field(default=1.0, ge=0.1, le=5)

    @field_validator("key")
    @classmethod
    def _key(cls, value: str) -> str:
        if not _KEY.match(value):
            raise ValueError("lower-case letters, digits and underscores, starting with a letter")
        return value


class InterviewTypeAdmin(InterviewTypeOut):
    enabled: bool
    max_followups: int
    rubric: list[RubricCriterion]
    sort_order: int
    updated_at: datetime


class InterviewTypeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=120)
    question_count: int | None = Field(default=None, ge=1, le=10)
    max_followups: int | None = Field(default=None, ge=0, le=6)
    difficulty: Difficulty | None = None
    rubric: list[RubricCriterion] | None = Field(default=None, min_length=1, max_length=10)

    @field_validator("rubric")
    @classmethod
    def _unique(cls, value: list[RubricCriterion] | None) -> list[RubricCriterion] | None:
        if value is not None and len({c.key for c in value}) != len(value):
            raise ValueError("Rubric keys must be unique")
        return value


class AdminInterviewOut(BaseModel):
    id: uuid.UUID
    user_email: str
    type_key: str
    status: InterviewStatus
    difficulty: Difficulty
    job_title: str | None
    created_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    hints_used: int
    report_status: ReportStatus | None
    overall_score: int | None


class PromptSummary(BaseModel):
    name: str
    description: str
    active_version: int | None
    versions: int
    updated_at: datetime


class PromptVersionOut(BaseModel):
    version: int
    system: str
    user: str
    notes: str | None
    source: str
    created_by_email: str | None
    created_at: datetime
    active: bool


class PromptDetail(BaseModel):
    name: str
    description: str
    active_version: int | None
    variables: list[str]  # what a template may use
    sample: dict[str, Any]  # example values for the playground
    versions: list[PromptVersionOut]  # newest first


class PromptVersionCreate(BaseModel):
    system: str = Field(min_length=1, max_length=20000)
    user: str = Field(default="", max_length=20000)
    notes: str | None = Field(default=None, max_length=500)
    activate: bool = False


class PromptActivate(BaseModel):
    version: int = Field(ge=1)


class PromptTest(BaseModel):
    """Render and run a version (or unsaved text) with example variables."""

    version: int | None = None
    system: str | None = Field(default=None, max_length=20000)
    user: str | None = Field(default=None, max_length=20000)
    variables: dict[str, Any] = Field(default_factory=dict)


class PromptTestResult(BaseModel):
    messages: list[dict[str, str]]
    output: str
    provider: str
    model: str
    latency_ms: int
