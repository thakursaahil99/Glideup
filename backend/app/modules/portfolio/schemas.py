"""What a portfolio analysis produces, and what the LLM must return for a website.

Same rules as resumes: forgiving about shape, strict about bounds, links are plain
http(s) only, and skills are canonicalised so they merge with resume skills.
"""

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.modules.resumes.schemas import OptionalText, ParsedSkill, SkillCategory
from app.modules.resumes.skills import canonicalize


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


def _drop_blank_items(value: object) -> object:
    if value is None:
        return []
    if isinstance(value, list):
        return [v for v in value if v is not None and not (isinstance(v, str) and not v.strip())]
    return value


def _safe_url(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value if re.match(r"^https?://", value, re.I) else f"https://{value}"
    return candidate if re.match(r"^https?://[\w.-]+\.[a-z]{2,}(/\S*)?$", candidate, re.I) else None


class Project(_Model):
    name: str = Field(min_length=1, max_length=200)
    description: OptionalText = Field(default=None, max_length=500)
    url: OptionalText = Field(default=None, max_length=300)
    technologies: list[Annotated[str, Field(max_length=100)]] = Field(
        default_factory=list, max_length=15
    )
    stars: int | None = Field(default=None, ge=0)

    @field_validator("technologies", mode="before")
    @classmethod
    def _null_list(cls, value: object) -> object:
        return _drop_blank_items(value)

    @field_validator("url")
    @classmethod
    def _plain_link(cls, value: str | None) -> str | None:
        return _safe_url(value)


class ParsedPortfolio(_Model):
    """The LLM's structured reading of a portfolio website."""

    headline: OptionalText = Field(default=None, max_length=200)
    summary: OptionalText = Field(default=None, max_length=1000)
    skills: list[ParsedSkill] = Field(default_factory=list, max_length=100)
    projects: list[Project] = Field(default_factory=list, max_length=20)

    @field_validator("skills", "projects", mode="before")
    @classmethod
    def _null_list(cls, value: object) -> object:
        # Models emit null lists and null/blank items; drop them instead of failing.
        return _drop_blank_items(value)


class PortfolioSkill(_Model):
    name: str = Field(min_length=1, max_length=100)
    category: SkillCategory | None = None
    # Why we believe it, shown to the user: "Primary language of 7 repositories".
    evidence: OptionalText = Field(default=None, max_length=200)


class PortfolioResult(_Model):
    """Stored on `PortfolioAnalysis.result` and returned by the API."""

    headline: OptionalText = Field(default=None, max_length=200)
    summary: OptionalText = Field(default=None, max_length=1000)
    skills: list[PortfolioSkill] = Field(default_factory=list, max_length=100)
    projects: list[Project] = Field(default_factory=list, max_length=20)
    # GitHub only: {"public_repos": 30, "followers": 12, ...}
    stats: dict[str, int] = Field(default_factory=dict)
    # GitHub only: primary language -> number of repositories.
    languages: dict[str, int] = Field(default_factory=dict)

    @field_validator("skills")
    @classmethod
    def _canonical_unique(cls, skills: list[PortfolioSkill]) -> list[PortfolioSkill]:
        merged: dict[str, PortfolioSkill] = {}
        for skill in skills:
            canonical = canonicalize(skill.name)
            if canonical.normalized in merged:
                continue
            merged[canonical.normalized] = skill.model_copy(
                update={"name": canonical.name, "category": skill.category or canonical.category}
            )
        return list(merged.values())
