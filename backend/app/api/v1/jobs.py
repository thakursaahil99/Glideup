import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import StringConstraints

from app.api.deps import CurrentUser, SessionDep
from app.api.v1.job_schemas import JobCard, JobDetail, JobSearchResponse, SavedJobOut
from app.core.errors import ErrorResponse
from app.db.models import ExperienceLevel, Job, WorkMode
from app.modules.jobs import service
from app.modules.jobs.ingestion import salary_text
from app.modules.jobs.search import Region, RemoteFilter, SearchQuery, Sort

router = APIRouter(
    prefix="/jobs",
    tags=["jobs"],
    responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)


def to_card(job: Job, *, saved: bool) -> JobCard:
    return JobCard(
        id=job.id,
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        country=job.country,
        countries=job.countries,
        states=job.states,
        cities=job.cities,
        remote_scope=job.remote_scope,
        work_mode=job.work_mode,
        experience_level=job.experience_level,
        employment_type=job.employment_type,
        skills=job.skills[:12],
        posted_at=job.posted_at,
        first_seen_at=job.first_seen_at,
        salary=salary_text(job),
        is_featured=job.is_featured,
        is_saved=saved,
        source=job.source.key,
        attribution=service.attribution_for(job),
    )


@router.get("", response_model=JobSearchResponse, responses={400: {"model": ErrorResponse}})
async def search_jobs(
    session: SessionDep,
    user: CurrentUser,
    q: Annotated[str, Query(max_length=200)] = "",
    location: Annotated[
        str | None, Query(max_length=100, description="Free text; prefer country/state/city")
    ] = None,
    country: Annotated[
        list[Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")]] | None,
        Query(max_length=20, description="ISO 3166-1 alpha-2, e.g. IN"),
    ] = None,
    state: Annotated[list[str] | None, Query(max_length=20)] = None,
    city: Annotated[list[str] | None, Query(max_length=20)] = None,
    remote: Annotated[
        RemoteFilter | None,
        Query(description="india = Remote - India; worldwide = no country limit"),
    ] = None,
    region: Annotated[
        Region | None, Query(description="Quick India / International toggle")
    ] = None,
    work_mode: Annotated[list[WorkMode] | None, Query()] = None,
    experience: Annotated[list[ExperienceLevel] | None, Query()] = None,
    skills: Annotated[list[str] | None, Query(max_length=10)] = None,
    company: Annotated[list[str] | None, Query(max_length=20)] = None,
    posted_within_days: Annotated[int | None, Query(ge=1, le=90)] = None,
    sort: Sort = "relevance",
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = service.PAGE_SIZE,
) -> JobSearchResponse:
    """Search open jobs. Paginate with the opaque `next_cursor` from the previous page."""
    query = SearchQuery(
        q=q.strip(),
        location=location.strip() if location and location.strip() else None,
        countries=tuple(country or []),
        states=tuple(s.strip() for s in state or [] if s.strip()),
        cities=tuple(c.strip() for c in city or [] if c.strip()),
        remote=remote,
        region=region,
        work_modes=tuple(m.value for m in work_mode or []),
        levels=tuple(lv.value for lv in experience or []),
        skills=tuple(s.strip() for s in skills or [] if s.strip()),
        companies=tuple(c.strip() for c in company or [] if c.strip()),
        posted_within_days=posted_within_days,
        sort=sort,
        offset=service.decode_cursor(cursor),
        limit=limit,
    )
    page = await service.search_jobs(session, user, query)
    return JobSearchResponse(
        items=[to_card(j, saved=j.id in page.saved_ids) for j in page.jobs],
        next_cursor=page.next_cursor,
        total=page.hits.total,
        facets=page.hits.facets,
        search_backend=page.hits.backend,
        took_ms=page.hits.took_ms,
    )


@router.get("/saved", response_model=list[SavedJobOut])
async def saved_jobs(session: SessionDep, user: CurrentUser) -> list[SavedJobOut]:
    return [
        SavedJobOut(saved_at=s.created_at, job=to_card(s.job, saved=True))
        for s in await service.list_saved(session, user)
    ]


@router.get("/{job_id}", response_model=JobDetail)
async def get_job(job_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> JobDetail:
    job = await service.get_job(session, job_id)
    card = to_card(job, saved=await service.is_saved(session, user, job.id))
    return JobDetail(
        **card.model_dump(),
        department=job.department,
        description_html=job.description_html,
        apply_url=job.apply_url,
        is_active=job.is_active,
        last_seen_at=job.last_seen_at,
    )


@router.put("/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def save_job(job_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await service.save_job(session, user, job_id)


@router.delete("/{job_id}/save", status_code=status.HTTP_204_NO_CONTENT)
async def unsave_job(job_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await service.unsave_job(session, user, job_id)
