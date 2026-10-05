"""Matching: per-job score and skill gap, AI analysis, and recommendations."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from pydantic import StringConstraints

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.jobs import to_card
from app.api.v1.match_schemas import (
    AnalysisOut,
    LevelFit,
    MatchDetail,
    MatchedSkill,
    PracticeStack,
    RecommendationsResponse,
    RecommendedJob,
    ScoreParts,
    TransferableSkill,
    percent,
    summary_of,
)
from app.core.config import get_settings
from app.core.errors import ErrorResponse
from app.core.ratelimit import rate_limit
from app.db.models import Job, JobMatch
from app.modules.jobs import service as jobs
from app.modules.matching import service
from app.modules.matching.schemas import SkillGapAnalysis
from app.modules.resumes.skills import canonicalize

router = APIRouter(
    tags=["matches"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def _analysis_out(row: JobMatch | None, stale: bool) -> AnalysisOut | None:
    if row is None:
        return None
    return AnalysisOut(
        status=row.status,
        stale=stale,
        result=SkillGapAnalysis.model_validate(row.analysis) if row.analysis else None,
        error=row.error,
        requested_at=row.requested_at,
        analyzed_at=row.analyzed_at,
        analyzed_by=row.analyzed_by,
    )


async def _detail(session: SessionDep, user: CurrentUser, job: Job) -> MatchDetail:
    view = await service.match_view(session, user.id, job)
    languages, frameworks = service.practice_stack(job)
    match, candidate = view.match, view.candidate
    sources = candidate.sources if candidate else {}
    return MatchDetail(
        available=candidate is not None,
        summary=summary_of(match) if match else None,
        parts=ScoreParts(
            semantic=percent(match.semantic),
            skills=percent(match.skills),
            level=percent(match.level),
        )
        if match
        else None,
        matched=[
            MatchedSkill(name=name, sources=sources.get(canonicalize(name).normalized, []))
            for name in (match.matched if match else [])
        ],
        transferable=[
            TransferableSkill(skill=t.skill, via=t.via)
            for t in (match.transferable if match else [])
        ],
        missing=match.missing if match else [],
        level=LevelFit(
            job_level=job.experience_level, your_years=candidate.years if candidate else None
        ),
        practice=PracticeStack(languages=languages, frameworks=frameworks),
        embedding_pending=bool(candidate and candidate.embedding_pending),
        analysis=_analysis_out(view.analysis, view.analysis_stale),
        analyses_per_day=get_settings().match_analysis_daily_limit,
    )


@router.get("/jobs/{job_id}/match", response_model=MatchDetail)
async def job_match(job_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> MatchDetail:
    """Your score for this job, the skills behind it, and any AI skill-gap analysis."""
    job = await service.get_listed_job(session, job_id)
    return await _detail(session, user, job)


@router.post(
    "/jobs/{job_id}/match/analysis",
    response_model=MatchDetail,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    dependencies=[Depends(rate_limit("llm"))],
)
async def analyze_match(job_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> MatchDetail:
    """Start an AI skill-gap analysis (runs in the background; poll the match endpoint).
    Reuses a fresh or running analysis instead of starting another."""
    job = await service.get_listed_job(session, job_id)
    await service.request_analysis(session, user.id, job)
    return await _detail(session, user, job)


@router.get("/matches/recommended", response_model=RecommendationsResponse)
async def recommended(
    session: SessionDep,
    user: CurrentUser,
    country: Annotated[
        list[Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]] | None,
        Query(max_length=10, description="Only jobs in these countries (ISO 3166-1 alpha-2)"),
    ] = None,
    remote: Annotated[bool, Query(description="Only remote jobs")] = False,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = jobs.PAGE_SIZE,
) -> RecommendationsResponse:
    """Jobs ranked by how well they fit you, nudged by your preferred locations and
    remote preference."""
    offset = jobs.decode_cursor(cursor)
    candidate, ranked = await service.recommend(
        session, user.id, countries=tuple(country or []), remote_only=remote
    )
    page = ranked[offset : offset + limit]
    saved = await jobs.saved_ids(session, user, [r.job.id for r in page])
    items = []
    for rec in page:
        card = to_card(rec.job, saved=rec.job.id in saved)
        card.match = summary_of(rec.match)
        items.append(RecommendedJob(job=card, reasons=rec.reasons))
    end = offset + limit
    return RecommendationsResponse(
        available=candidate is not None,
        items=items,
        next_cursor=jobs.encode_cursor(end) if end < len(ranked) else None,
        total=len(ranked),
        embedding_pending=bool(candidate and candidate.embedding_pending),
    )
