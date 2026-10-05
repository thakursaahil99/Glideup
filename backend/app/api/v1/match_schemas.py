"""Request/response models for matching: score breakdown, skill gap and recommendations."""

from datetime import datetime

from pydantic import BaseModel, Field

from app.api.v1.job_schemas import JobCard, MatchSummary
from app.db.models import ExperienceLevel, MatchAnalysisStatus
from app.modules.matching.schemas import SkillGapAnalysis
from app.modules.matching.scoring import MatchResult


class MatchedSkill(BaseModel):
    name: str
    sources: list[str]  # "resume", "github", "website"


class TransferableSkill(BaseModel):
    skill: str  # what the job asks for
    via: str  # the related skill you have


class ScoreParts(BaseModel):
    """Each signal as a percentage, or null when it couldn't be judged."""

    semantic: int | None = Field(description="Resume vs job description similarity")
    skills: int | None = Field(description="Share of the job's skills you have")
    level: int | None = Field(description="Your years vs the level the job implies")


class LevelFit(BaseModel):
    job_level: ExperienceLevel
    your_years: float | None


class PracticeStack(BaseModel):
    """What 'Take a skill test' pre-selects for this job."""

    languages: list[str]
    frameworks: list[str]


class AnalysisOut(BaseModel):
    status: MatchAnalysisStatus
    stale: bool  # your resume, skills or the job changed since; refresh for a new one
    result: SkillGapAnalysis | None
    error: str | None
    requested_at: datetime
    analyzed_at: datetime | None
    analyzed_by: str | None


class MatchDetail(BaseModel):
    available: bool  # False until we know something about you (resume or GitHub)
    summary: MatchSummary | None
    parts: ScoreParts | None
    matched: list[MatchedSkill]
    transferable: list[TransferableSkill]
    missing: list[str]
    level: LevelFit
    practice: PracticeStack
    embedding_pending: bool  # your resume is still being embedded; the score is partial
    analysis: AnalysisOut | None
    analyses_per_day: int


class RecommendedJob(BaseModel):
    job: JobCard
    reasons: list[str]


class RecommendationsResponse(BaseModel):
    available: bool
    items: list[RecommendedJob]
    next_cursor: str | None
    total: int
    embedding_pending: bool


def summary_of(match: MatchResult) -> MatchSummary:
    return MatchSummary(
        score=match.score,
        label=match.label,
        partial=match.partial,
        matched_skills=len(match.matched),
        total_skills=len(match.matched) + len(match.transferable) + len(match.missing),
    )


def percent(value: float | None) -> int | None:
    return None if value is None else round(value * 100)
