"""The structured resume the LLM must produce (and the user can edit).

Validation is deliberately forgiving about *shape* (models return "5 years", "", nulls)
but strict about *bounds*, so whatever is stored is clean and safe to render.
"""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

from app.modules.resumes.skills import canonicalize

SkillCategory = Literal[
    "language", "framework", "database", "cloud", "devops", "tool", "practice", "soft", "other"
]
SkillLevel = Literal["beginner", "intermediate", "advanced", "expert"]


def _blank_to_none(value: object) -> object:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _to_years(value: object) -> object:
    """Accept 5, 5.5, "5", "5+ years", "" -> clean float in [0, 60] or None."""
    value = _blank_to_none(value)
    if isinstance(value, str):
        match = re.search(r"\d+(?:\.\d+)?", value)
        value = float(match.group()) if match else None
    if isinstance(value, int | float):
        return round(min(max(float(value), 0.0), 60.0), 1)
    return value


OptionalText = Annotated[str | None, BeforeValidator(_blank_to_none)]
Years = Annotated[float | None, BeforeValidator(_to_years)]


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


class ParsedSkill(_Model):
    name: str = Field(min_length=1, max_length=100)
    category: SkillCategory | None = None
    years: Years = None
    level: SkillLevel | None = None

    @field_validator("category", "level", mode="before")
    @classmethod
    def _lower(cls, value: object) -> object:
        value = _blank_to_none(value)
        return value.lower() if isinstance(value, str) else value

    @field_validator("category", mode="before")
    @classmethod
    def _unknown_category(cls, value: object) -> object:
        allowed = SkillCategory.__args__  # type: ignore[attr-defined]
        return value if value is None or value in allowed else "other"

    @field_validator("level", mode="before")
    @classmethod
    def _unknown_level(cls, value: object) -> object:
        allowed = SkillLevel.__args__  # type: ignore[attr-defined]
        return value if value is None or value in allowed else None


class Experience(_Model):
    title: str = Field(min_length=1, max_length=200)
    company: str = Field(min_length=1, max_length=200)
    location: OptionalText = Field(default=None, max_length=200)
    start: OptionalText = Field(default=None, max_length=20)
    end: OptionalText = Field(default=None, max_length=20)
    highlights: list[Annotated[str, Field(max_length=500)]] = Field(
        default_factory=list, max_length=8
    )


class Education(_Model):
    degree: str = Field(min_length=1, max_length=200)
    institution: str = Field(min_length=1, max_length=200)
    year: OptionalText = Field(default=None, max_length=20)

    @field_validator("year", mode="before")
    @classmethod
    def _year_to_text(cls, value: object) -> object:
        return str(value) if isinstance(value, int) else value


class ParsedResume(_Model):
    full_name: OptionalText = Field(default=None, max_length=200)
    headline: OptionalText = Field(default=None, max_length=200)
    summary: OptionalText = Field(default=None, max_length=2000)
    total_years_experience: Years = None
    location: OptionalText = Field(default=None, max_length=200)
    skills: list[ParsedSkill] = Field(default_factory=list, max_length=150)
    experience: list[Experience] = Field(default_factory=list, max_length=30)
    education: list[Education] = Field(default_factory=list, max_length=15)
    certifications: list[Annotated[str, Field(max_length=200)]] = Field(
        default_factory=list, max_length=30
    )
    links: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list, max_length=15)

    @field_validator("skills", "experience", "education", "certifications", "links", mode="before")
    @classmethod
    def _null_list(cls, value: object) -> object:
        # Models emit null lists and null/blank items; drop them instead of failing the parse.
        if value is None:
            return []
        if isinstance(value, list):
            return [
                v for v in value if v is not None and not (isinstance(v, str) and not v.strip())
            ]
        return value

    @field_validator("skills")
    @classmethod
    def _canonical_unique_skills(cls, skills: list[ParsedSkill]) -> list[ParsedSkill]:
        """Canonicalise names and merge duplicates, keeping the most informative entry."""
        merged: dict[str, ParsedSkill] = {}
        for skill in skills:
            canonical = canonicalize(skill.name)
            candidate = skill.model_copy(
                update={"name": canonical.name, "category": skill.category or canonical.category}
            )
            existing = merged.get(canonical.normalized)
            if existing is None or (candidate.years or 0) > (existing.years or 0):
                merged[canonical.normalized] = candidate
        return sorted(merged.values(), key=lambda s: (-(s.years or 0), s.name.lower()))

    @field_validator("links")
    @classmethod
    def _safe_links(cls, links: list[str]) -> list[str]:
        # Only plain web links: these are rendered as <a href>, so no javascript: etc.
        safe = []
        for link in links:
            candidate = link if re.match(r"^https?://", link, re.I) else f"https://{link}"
            if re.match(r"^https?://[\w.-]+\.[a-z]{2,}(/\S*)?$", candidate, re.I):
                safe.append(candidate)
        return safe
