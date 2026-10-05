import uuid
from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser, SessionDep
from app.core.errors import ErrorResponse
from app.db.models import AnalysisStatus, PortfolioAnalysis, PortfolioKind
from app.modules.portfolio import service, tasks
from app.modules.portfolio.schemas import PortfolioResult
from app.workers.runtime import dispatch

router = APIRouter(
    prefix="/portfolio",
    tags=["portfolio"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=300, description="GitHub profile or portfolio site")


class PortfolioAnalysisOut(BaseModel):
    id: uuid.UUID
    kind: PortfolioKind
    url: str
    status: AnalysisStatus
    error: str | None
    result: PortfolioResult | None
    analyzed_by: str | None
    analyzed_at: datetime | None
    updated_at: datetime


def to_out(analysis: PortfolioAnalysis) -> PortfolioAnalysisOut:
    return PortfolioAnalysisOut(
        id=analysis.id,
        kind=analysis.kind,
        url=analysis.url,
        status=analysis.status,
        error=analysis.error,
        result=PortfolioResult.model_validate(analysis.result) if analysis.result else None,
        analyzed_by=analysis.analyzed_by,
        analyzed_at=analysis.analyzed_at,
        updated_at=analysis.updated_at,
    )


@router.get("/analyses", response_model=list[PortfolioAnalysisOut])
async def list_analyses(session: SessionDep, user: CurrentUser) -> list[PortfolioAnalysisOut]:
    return [to_out(a) for a in await service.list_for_user(session, user.id)]


@router.post(
    "/analyses",
    response_model=PortfolioAnalysisOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def analyze(
    body: AnalyzeRequest, session: SessionDep, user: CurrentUser
) -> PortfolioAnalysisOut:
    """Analyze a GitHub profile or portfolio site in the background; poll GET /analyses.

    Analyzing a new link of the same kind replaces the previous analysis.
    """
    analysis = await service.request_analysis(session, user, body.url)
    await session.commit()
    dispatch(tasks.analyze_portfolio, service.analyze_job, str(analysis.id))
    await session.refresh(analysis)
    return to_out(analysis)


@router.post(
    "/analyses/{analysis_id}/retry",
    response_model=PortfolioAnalysisOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}},
)
async def retry(
    analysis_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> PortfolioAnalysisOut:
    analysis = await service.get_owned(session, user, analysis_id)
    analysis = await service.request_analysis(session, user, analysis.url)
    await session.commit()
    dispatch(tasks.analyze_portfolio, service.analyze_job, str(analysis.id))
    await session.refresh(analysis)
    return to_out(analysis)


@router.delete("/analyses/{analysis_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(analysis_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await service.delete(session, await service.get_owned(session, user, analysis_id))


class CombinedSkillOut(BaseModel):
    name: str
    category: str | None
    sources: list[str]


@router.get("/skills", response_model=list[CombinedSkillOut])
async def combined_skills(session: SessionDep, user: CurrentUser) -> list[CombinedSkillOut]:
    """All of the user's skills: active resume plus finished portfolio analyses."""
    return [
        CombinedSkillOut(name=s.name, category=s.category, sources=s.sources)
        for s in await service.user_skills(session, user.id)
    ]
