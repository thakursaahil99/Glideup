"""Structured data for interviews: the question plan, and the report the LLM writes.

LLM output is forgiving about shape (null lists, scores as strings or out of range) but
strict about bounds; the report is then grounded and scored by `report.py`, never trusted
as-is.
"""

from typing import Annotated, Any, Literal

from annotated_types import MaxLen
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.resumes.schemas import OptionalText

QuestionKind = Literal["coding", "design", "behavioral", "technical"]
ShortText = Annotated[str, Field(max_length=300)]


ITEM_CHARS = 300  # every list of strings here holds ShortText items


class _Model(BaseModel):
    """Small models write long. Text and lists over a limit are clipped, not rejected:
    one rambling sentence must not throw away a whole report."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    @model_validator(mode="before")
    @classmethod
    def _clip(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name, field in cls.model_fields.items():
            value = data.get(name)
            limit = next((m.max_length for m in field.metadata if isinstance(m, MaxLen)), None)
            if isinstance(value, str) and limit:
                data[name] = value[:limit]
            elif isinstance(value, list):
                items = value[:limit] if limit else value
                data[name] = [v[:ITEM_CHARS] if isinstance(v, str) else v for v in items]
        return data


def _drop_blank_items(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v is not None and not (isinstance(v, str) and not v.strip())]
    return value


def _clamped_int(value: object, low: int, high: int) -> int:
    try:
        number = round(float(str(value).split("/")[0]))  # "4", 4.4, "4/5"
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


class PlanQuestion(_Model):
    prompt: str = Field(min_length=5, max_length=1000)
    focus: str = Field(default="General", max_length=100)
    kind: QuestionKind = "technical"
    expected_points: list[ShortText] = Field(default_factory=list, max_length=8)

    @field_validator("expected_points", mode="before")
    @classmethod
    def _points(cls, value: object) -> object:
        return _drop_blank_items(value)

    @field_validator("kind", mode="before")
    @classmethod
    def _kind(cls, value: object) -> object:
        text = str(value or "").lower()
        for kind in ("coding", "design", "behavioral"):
            if kind in text:
                return kind
        return "technical"


class InterviewPlan(_Model):
    """What the `interview_plan` prompt returns for a job-specific interview."""

    questions: list[PlanQuestion] = Field(min_length=1, max_length=10)


class CriterionScore(_Model):
    key: str = Field(max_length=50)
    score: int = Field(ge=1, le=5)
    evidence: OptionalText = Field(default=None, max_length=300)  # a quote from the candidate
    comment: OptionalText = Field(default=None, max_length=300)

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, value: object) -> int:
        return _clamped_int(value, 1, 5)


class QuestionScore(_Model):
    index: int = Field(ge=0, le=20)
    score: int = Field(ge=0, le=10)
    feedback: OptionalText = Field(default=None, max_length=500)
    strengths: list[ShortText] = Field(default_factory=list, max_length=4)
    improvements: list[ShortText] = Field(default_factory=list, max_length=4)

    @field_validator("score", mode="before")
    @classmethod
    def _score(cls, value: object) -> int:
        return _clamped_int(value, 0, 10)

    @field_validator("strengths", "improvements", mode="before")
    @classmethod
    def _lists(cls, value: object) -> object:
        return _drop_blank_items(value)


class NextPractice(_Model):
    type: str = Field(max_length=30)
    focus: str = Field(max_length=100)
    reason: OptionalText = Field(default=None, max_length=300)


class ReportDraft(_Model):
    """What the `interview_report` prompt returns."""

    summary: str = Field(min_length=1, max_length=800)
    criteria: list[CriterionScore] = Field(default_factory=list, max_length=12)
    questions: list[QuestionScore] = Field(default_factory=list, max_length=12)
    strengths: list[ShortText] = Field(default_factory=list, max_length=6)
    weaknesses: list[ShortText] = Field(default_factory=list, max_length=6)
    tips: list[ShortText] = Field(default_factory=list, max_length=6)
    next_practice: NextPractice | None = None

    @field_validator("criteria", "questions", "strengths", "weaknesses", "tips", mode="before")
    @classmethod
    def _lists(cls, value: object) -> object:
        return _drop_blank_items(value)


class ScoredCriterion(_Model):
    key: str
    name: str
    weight: float
    score: int | None  # 1-5; None if the model didn't judge it
    evidence: str | None = None
    comment: str | None = None


class ScoredQuestion(_Model):
    index: int
    prompt: str
    focus: str
    answered: bool
    score: int  # 0-10
    feedback: str | None = None
    strengths: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class ReportResult(_Model):
    """Stored on InterviewReport.result and returned by the API."""

    overall_score: int  # 0-100, computed by us from the parts below
    rubric_score: int | None  # 0-100
    questions_score: int  # 0-100, unanswered questions count as 0
    summary: str
    criteria: list[ScoredCriterion]
    questions: list[ScoredQuestion]
    strengths: list[str]
    weaknesses: list[str]
    tips: list[str]
    next_practice: NextPractice | None
    answered: int
    total_questions: int
    hints_used: int
