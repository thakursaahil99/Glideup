"""What the LLM returns for a skill-gap analysis, and how we keep it honest.

The model is forgiving about shape (null lists, blank items) but strict about bounds.
`ground()` then removes anything not supported by the inputs: a "missing" skill must be
mentioned in the job posting and must not be something the candidate already has; a
"weak" skill must be one the candidate actually lists. A model that invents requirements
or misreads the resume can make the answer shorter, never wrong in that way.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.resumes.schemas import OptionalText
from app.modules.resumes.skills import _alias_pattern, canonicalize


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _drop_blank_items(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v is not None and not (isinstance(v, str) and not v.strip())]
    return value


class MissingSkill(_Model):
    skill: str = Field(min_length=1, max_length=100)
    importance: Literal["required", "preferred"] = "required"
    reason: OptionalText = Field(default=None, max_length=300)
    suggestion: OptionalText = Field(default=None, max_length=300)

    @field_validator("importance", mode="before")
    @classmethod
    def _importance(cls, value: object) -> object:
        text = str(value or "").lower()
        return (
            "preferred"
            if any(w in text for w in ("prefer", "nice", "bonus", "plus"))
            else "required"
        )


class WeakSkill(_Model):
    skill: str = Field(min_length=1, max_length=100)
    reason: OptionalText = Field(default=None, max_length=300)
    suggestion: OptionalText = Field(default=None, max_length=300)


class SkillGapAnalysis(_Model):
    summary: str = Field(min_length=1, max_length=600)
    strengths: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=6
    )
    missing: list[MissingSkill] = Field(default_factory=list, max_length=10)
    weak: list[WeakSkill] = Field(default_factory=list, max_length=8)

    @field_validator("strengths", "missing", "weak", mode="before")
    @classmethod
    def _null_list(cls, value: object) -> object:
        return _drop_blank_items(value)


def _mentioned(skill: str, haystack: str, job_skills: set[str]) -> bool:
    canonical = canonicalize(skill)
    if canonical.normalized in job_skills:
        return True
    return bool(_alias_pattern(skill).search(haystack)) or bool(
        _alias_pattern(canonical.name).search(haystack)
    )


def ground(
    analysis: SkillGapAnalysis,
    *,
    job_text: str,
    job_skills: list[str],
    candidate_skills: set[str],
) -> SkillGapAnalysis:
    """Drop claims the inputs don't support. `candidate_skills` holds normalised keys."""
    job_keys = {canonicalize(s).normalized for s in job_skills}
    haystack = re.sub(r"\s+", " ", job_text)
    seen: set[str] = set()
    missing: list[MissingSkill] = []
    for item in analysis.missing:
        key = canonicalize(item.skill).normalized
        if key in seen or key in candidate_skills or not _mentioned(item.skill, haystack, job_keys):
            continue
        seen.add(key)
        missing.append(item.model_copy(update={"skill": canonicalize(item.skill).name}))
    weak: list[WeakSkill] = []
    for weak_item in analysis.weak:
        key = canonicalize(weak_item.skill).normalized
        if key in seen or key not in candidate_skills:
            continue
        seen.add(key)
        weak.append(weak_item.model_copy(update={"skill": canonicalize(weak_item.skill).name}))
    return analysis.model_copy(update={"missing": missing, "weak": weak})
