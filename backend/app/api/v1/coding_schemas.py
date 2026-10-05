"""Request/response models for coding practice and the question bank admin."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import Difficulty, GenerationStatus, QuestionStatus, Verdict

MAX_CODE = 50_000


class LanguageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    time_limit_s: float
    memory_limit_mb: int


class LanguageAdmin(LanguageOut):
    enabled: bool
    sort_order: int


class LanguageUpdate(BaseModel):
    enabled: bool | None = None
    time_limit_s: float | None = Field(default=None, ge=0.5, le=20)
    memory_limit_mb: int | None = Field(default=None, ge=32, le=2048)


class ProblemSummary(BaseModel):
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    solved: bool
    attempted: bool


class ExampleOut(BaseModel):
    input: str
    expected_output: str


class ProblemDetail(BaseModel):
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    statement: str
    examples: list[ExampleOut]
    hidden_tests: int
    starters: dict[str, str]  # language key -> starter code
    languages: list[LanguageOut]


class CodeIn(BaseModel):
    language: str = Field(max_length=20)
    code: str = Field(min_length=1, max_length=MAX_CODE)


class CaseResultOut(BaseModel):
    position: int
    hidden: bool
    verdict: Verdict
    time_ms: int | None = None
    memory_kb: int | None = None
    input: str | None = None  # visible tests only
    expected: str | None = None
    stdout: str | None = None
    stderr: str | None = None


class RunResultOut(BaseModel):
    verdict: Verdict
    passed: int
    total: int
    results: list[CaseResultOut]
    compile_output: str | None
    max_time_ms: int | None


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    language_key: str
    verdict: Verdict
    passed: int
    total: int
    results: list[CaseResultOut]
    compile_output: str | None
    max_time_ms: int | None
    created_at: datetime
    finished_at: datetime | None


class SubmissionDetail(SubmissionOut):
    code: str


# --- admin ---


class TemplateIn(BaseModel):
    language_key: str = Field(max_length=20)
    starter_code: str = Field(default="", max_length=MAX_CODE)
    reference_solution: str | None = Field(default=None, max_length=MAX_CODE)


class TestCaseIn(BaseModel):
    input: str = Field(default="", max_length=2_000_000)
    expected_output: str = Field(default="", max_length=2_000_000)
    hidden: bool = True


class QuestionIn(BaseModel):
    slug: str = Field(min_length=3, max_length=100, pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")
    title: str = Field(min_length=3, max_length=200)
    difficulty: Difficulty
    topics: list[str] = Field(default_factory=list, max_length=8)
    statement: str = Field(min_length=10, max_length=20000)
    templates: list[TemplateIn] = Field(default_factory=list, max_length=12)
    tests: list[TestCaseIn] = Field(min_length=1, max_length=100)

    @field_validator("topics")
    @classmethod
    def _topics(cls, value: list[str]) -> list[str]:
        return [t.strip().lower()[:40] for t in value if t.strip()]


class QuestionAdminSummary(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    status: QuestionStatus
    source: str
    validated: bool
    tests: int
    updated_at: datetime
    stats: dict[str, Any] | None


class QuestionAdminDetail(BaseModel):
    id: uuid.UUID
    slug: str
    title: str
    difficulty: Difficulty
    topics: list[str]
    statement: str
    status: QuestionStatus
    source: str
    validation: dict[str, Any] | None
    templates: list[TemplateIn]
    tests: list[TestCaseIn]
    stats: dict[str, Any] | None


class QuestionStatusUpdate(BaseModel):
    status: QuestionStatus


class GenerationRequest(BaseModel):
    topic: str = Field(min_length=2, max_length=100)
    difficulty: Difficulty = Difficulty.MEDIUM
    count: int = Field(default=1, ge=1, le=5)


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    topic: str
    difficulty: Difficulty
    status: GenerationStatus
    draft: dict[str, Any] | None
    validation: dict[str, Any] | None
    error: str | None
    generated_by: str | None
    question_id: uuid.UUID | None
    review_note: str | None
    created_at: datetime


class GenerationReview(BaseModel):
    approve: bool
    publish: bool = False
    note: str | None = Field(default=None, max_length=500)
