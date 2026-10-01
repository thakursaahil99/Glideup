"""Admin: job sources, company boards, individual jobs and the search index."""

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status

from app.api.deps import RequestMetaDep, SessionDep, require_permission
from app.api.v1.job_schemas import (
    AdminJobOut,
    CompanyCreate,
    CompanyImportResult,
    CompanyOut,
    CompanyUpdate,
    IngestionRunOut,
    JobFlagsUpdate,
    JobSourceOut,
    JobSourceUpdate,
    ReindexResult,
    RunStarted,
)
from app.api.v1.schemas import Page
from app.core.errors import AppError, ConflictError, ErrorResponse
from app.core.rbac import Permission
from app.db.models import IngestionRun, Job, JobSource, User
from app.jobsources.registry import get_plugin
from app.modules.audit import service as audit
from app.modules.jobs import catalog, service, tasks
from app.modules.jobs.ingestion import rebuild_search_index, run_ingestion, sync_search
from app.workers.runtime import dispatch

router = APIRouter(
    prefix="/admin",
    tags=["admin: jobs"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

JobsAdmin = Annotated[User, Depends(require_permission(Permission.JOBS_MANAGE))]
MAX_CSV_BYTES = 1024 * 1024


def _source_out(source: JobSource, last: IngestionRun | None) -> JobSourceOut:
    plugin = get_plugin(source.key)
    return JobSourceOut(
        key=source.key,
        name=source.name,
        enabled=source.enabled,
        schedule_minutes=source.schedule_minutes,
        rate_limit_per_minute=source.rate_limit_per_minute,
        config=source.config or {},
        uses_company_boards=plugin.uses_company_boards,
        config_options=plugin.config_options(),
        not_configured_reason=plugin.is_configured(source.config or {}),
        last_run_at=source.last_run_at,
        last_success_at=source.last_success_at,
        last_error=source.last_error,
        consecutive_failures=source.consecutive_failures,
        active_jobs=source.active_jobs,
        last_run=IngestionRunOut.model_validate(last) if last else None,
    )


# ------------------------------------------------------------------ sources


@router.get("/job-sources", response_model=list[JobSourceOut])
async def list_sources(session: SessionDep, _: JobsAdmin) -> list[JobSourceOut]:
    return [_source_out(s, last) for s, last in await service.list_sources(session)]


@router.patch("/job-sources/{key}", response_model=JobSourceOut)
async def update_source(
    key: str, body: JobSourceUpdate, session: SessionDep, actor: JobsAdmin, meta: RequestMetaDep
) -> JobSourceOut:
    source = await service.update_source(
        session, actor=actor, key=key, changes=body.model_dump(exclude_unset=True), meta=meta
    )
    runs = await service.list_runs(session, key, limit=1)
    return _source_out(source, runs[0] if runs else None)


@router.post(
    "/job-sources/{key}/run",
    response_model=RunStarted,
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"model": ErrorResponse}},
)
async def run_source_now(
    key: str, session: SessionDep, actor: JobsAdmin, meta: RequestMetaDep
) -> RunStarted:
    """Start an ingestion run now (in the background), even if the source is disabled."""
    source = await service.get_source(session, key)
    reason = get_plugin(source.key).is_configured(source.config or {})
    if reason:
        raise ConflictError(reason, code="source_not_configured")
    await audit.record(
        session,
        actor=actor,
        action="job_source.run_requested",
        target_type="job_source",
        target_id=key,
        meta=meta,
    )
    await session.commit()
    dispatch(tasks.ingest_source_task, run_ingestion, key, "manual", str(actor.id))
    return RunStarted(source=key)


@router.get("/job-sources/{key}/runs", response_model=list[IngestionRunOut])
async def list_runs(
    key: str,
    session: SessionDep,
    _: JobsAdmin,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[IngestionRunOut]:
    return [IngestionRunOut.model_validate(r) for r in await service.list_runs(session, key, limit)]


# ------------------------------------------------------------------ companies


@router.get("/companies", response_model=list[CompanyOut])
async def list_companies(
    session: SessionDep,
    _: JobsAdmin,
    search: Annotated[str | None, Query(max_length=100)] = None,
    ats: Annotated[Literal["greenhouse", "lever", "ashby"] | None, Query()] = None,
) -> list[CompanyOut]:
    return [
        CompanyOut.model_validate(c)
        for c in await service.list_companies(session, search=search, ats=ats)
    ]


@router.post(
    "/companies",
    response_model=CompanyImportResult,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def add_company(
    body: CompanyCreate, session: SessionDep, actor: JobsAdmin, meta: RequestMetaDep
) -> CompanyImportResult:
    row = {
        "name": body.name,
        "ats": body.ats.value,
        "board_token": body.board_token,
        "website": body.website or "",
    }
    result = await catalog.import_companies(session, [row])
    if not result.created:
        raise ConflictError("That company board is already in the list", code="company_exists")
    await audit.record(
        session,
        actor=actor,
        action="company.created",
        target_type="company",
        target_id=f"{body.ats.value}:{body.board_token}",
        after=row,
        meta=meta,
    )
    return CompanyImportResult(**result.__dict__)


@router.post("/companies/import", response_model=CompanyImportResult)
async def import_companies(
    session: SessionDep,
    actor: JobsAdmin,
    meta: RequestMetaDep,
    file: Annotated[
        UploadFile, File(description="CSV with columns name,ats,board_token[,website]")
    ],
) -> CompanyImportResult:
    data = await file.read(MAX_CSV_BYTES + 1)
    if len(data) > MAX_CSV_BYTES:
        raise AppError("CSV files can be at most 1 MB", code="file_too_large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise AppError("The CSV must be UTF-8 encoded", code="invalid_csv") from exc
    result = await catalog.import_companies(session, catalog.parse_company_csv(text))
    await audit.record(
        session,
        actor=actor,
        action="company.imported",
        target_type="company",
        after={"created": result.created, "updated": result.updated, "skipped": result.skipped},
        meta=meta,
    )
    return CompanyImportResult(**result.__dict__)


@router.patch("/companies/{company_id}", response_model=CompanyOut)
async def update_company(
    company_id: uuid.UUID,
    body: CompanyUpdate,
    session: SessionDep,
    actor: JobsAdmin,
    meta: RequestMetaDep,
) -> CompanyOut:
    company = await service.set_company_enabled(
        session, actor=actor, company_id=company_id, enabled=body.enabled, meta=meta
    )
    return CompanyOut.model_validate(company)


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_company(
    company_id: uuid.UUID, session: SessionDep, actor: JobsAdmin, meta: RequestMetaDep
) -> None:
    retired = await service.delete_company(session, actor=actor, company_id=company_id, meta=meta)
    await session.commit()
    await sync_search(retired)


# ------------------------------------------------------------------ jobs


async def _admin_job_out(session: SessionDep, job: Job) -> AdminJobOut:
    original = await session.get(Job, job.duplicate_of_id) if job.duplicate_of_id else None
    return AdminJobOut(
        id=job.id,
        title=job.title,
        company_name=job.company_name,
        location=job.location,
        source=job.source.key,
        is_active=job.is_active,
        is_hidden=job.is_hidden,
        is_featured=job.is_featured,
        duplicate_of_id=job.duplicate_of_id,
        duplicate_of_title=f"{original.title} · {original.company_name}" if original else None,
        first_seen_at=job.first_seen_at,
        last_seen_at=job.last_seen_at,
        apply_url=job.apply_url,
    )


@router.get("/jobs", response_model=Page[AdminJobOut])
async def list_jobs(
    session: SessionDep,
    _: JobsAdmin,
    search: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[
        Literal["listed", "hidden", "featured", "inactive", "duplicate"] | None,
        Query(alias="status"),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AdminJobOut]:
    jobs, total = await service.admin_list_jobs(
        session, search=search, status=status_filter, page=page, page_size=page_size
    )
    return Page(
        items=[await _admin_job_out(session, j) for j in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/jobs/{job_id}", response_model=AdminJobOut)
async def update_job(
    job_id: uuid.UUID,
    body: JobFlagsUpdate,
    session: SessionDep,
    actor: JobsAdmin,
    meta: RequestMetaDep,
) -> AdminJobOut:
    job = await service.set_job_flags(
        session, actor=actor, job_id=job_id, hidden=body.hidden, featured=body.featured, meta=meta
    )
    out = await _admin_job_out(session, job)
    await session.commit()
    await sync_search([job.id])
    return out


@router.post(
    "/jobs/{job_id}/not-duplicate",
    response_model=AdminJobOut,
    responses={409: {"model": ErrorResponse}},
)
async def mark_not_duplicate(
    job_id: uuid.UUID, session: SessionDep, actor: JobsAdmin, meta: RequestMetaDep
) -> AdminJobOut:
    job = await service.mark_not_duplicate(session, actor=actor, job_id=job_id, meta=meta)
    out = await _admin_job_out(session, job)
    await session.commit()
    await sync_search([job.id])
    return out


@router.post("/search/reindex", response_model=ReindexResult)
async def reindex(session: SessionDep, actor: JobsAdmin, meta: RequestMetaDep) -> ReindexResult:
    """Rebuild the search index from the database (after an outage, or a settings change)."""
    await audit.record(
        session, actor=actor, action="search.reindexed", target_type="search", meta=meta
    )
    await session.commit()
    return ReindexResult(indexed=await rebuild_search_index())
