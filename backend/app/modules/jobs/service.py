"""Job seeker use-cases (search, detail, saved jobs) and admin job management."""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import Company, IngestionRun, Job, JobSource, SavedJob, User
from app.jobsources.registry import PLUGINS, get_plugin
from app.modules.audit import service as audit
from app.modules.audit.service import RequestMeta
from app.modules.jobs.search import MAX_RESULTS, SearchHits, SearchQuery, get_search

PAGE_SIZE = 20


class InvalidCursorError(AppError):
    code = "invalid_cursor"


# ------------------------------------------------------------------ cursors


def encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(json.dumps({"o": offset}).encode()).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> int:
    """Opaque to clients, so the paging strategy can change without breaking them."""
    if not cursor:
        return 0
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        offset = int(json.loads(base64.urlsafe_b64decode(padded))["o"])
    except (ValueError, KeyError, TypeError, binascii.Error, json.JSONDecodeError) as exc:
        raise InvalidCursorError("This page link has expired. Please search again.") from exc
    if not 0 <= offset < MAX_RESULTS:
        raise InvalidCursorError("This page link has expired. Please search again.")
    return offset


# ------------------------------------------------------------------ job seekers


@dataclass
class SearchPage:
    jobs: list[Job]
    saved_ids: set[uuid.UUID]
    hits: SearchHits
    next_cursor: str | None


async def _saved_ids(session: AsyncSession, user: User, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    if not ids:
        return set()
    rows = await session.scalars(
        select(SavedJob.job_id).where(SavedJob.user_id == user.id, SavedJob.job_id.in_(ids))
    )
    return set(rows)


async def search_jobs(session: AsyncSession, user: User, query: SearchQuery) -> SearchPage:
    hits = await get_search().search(session, query)
    found = {j.id: j for j in await session.scalars(select(Job).where(Job.id.in_(hits.ids)))}
    # Keep the index's ranking; drop anything no longer listed (stale index entries).
    jobs = [found[i] for i in hits.ids if i in found and found[i].is_listed]
    end = query.offset + len(hits.ids)
    has_more = len(hits.ids) == query.limit and end < min(hits.total, MAX_RESULTS)
    return SearchPage(
        jobs=jobs,
        saved_ids=await _saved_ids(session, user, [j.id for j in jobs]),
        hits=hits,
        next_cursor=encode_cursor(end) if has_more else None,
    )


async def get_job(
    session: AsyncSession, job_id: uuid.UUID, *, include_unlisted: bool = False
) -> Job:
    job = await session.get(Job, job_id)
    if job is None or (not include_unlisted and job.is_hidden):
        raise NotFoundError("Job not found")
    return job


async def is_saved(session: AsyncSession, user: User, job_id: uuid.UUID) -> bool:
    return await session.get(SavedJob, (user.id, job_id)) is not None


async def save_job(session: AsyncSession, user: User, job_id: uuid.UUID) -> None:
    await get_job(session, job_id)
    if await session.get(SavedJob, (user.id, job_id)) is None:
        session.add(SavedJob(user_id=user.id, job_id=job_id))
        await session.flush()


async def unsave_job(session: AsyncSession, user: User, job_id: uuid.UUID) -> None:
    await session.execute(
        delete(SavedJob).where(SavedJob.user_id == user.id, SavedJob.job_id == job_id)
    )


async def list_saved(session: AsyncSession, user: User) -> list[SavedJob]:
    rows = await session.scalars(
        select(SavedJob).where(SavedJob.user_id == user.id).order_by(SavedJob.created_at.desc())
    )
    return [s for s in rows if not s.job.is_hidden]


def attribution_for(job: Job) -> str | None:
    plugin = PLUGINS.get(job.source.key)
    return plugin.attribution if plugin else None


# ------------------------------------------------------------------ admin: sources


async def list_sources(session: AsyncSession) -> list[tuple[JobSource, IngestionRun | None]]:
    sources = list(await session.scalars(select(JobSource).order_by(JobSource.key)))
    result = []
    for source in sources:
        last = await session.scalar(
            select(IngestionRun)
            .where(IngestionRun.source_id == source.id)
            .order_by(IngestionRun.started_at.desc())
            .limit(1)
        )
        result.append((source, last))
    return result


async def get_source(session: AsyncSession, key: str) -> JobSource:
    source = await session.scalar(select(JobSource).where(JobSource.key == key))
    if source is None:
        raise NotFoundError("Job source not found")
    return source


_SOURCE_FIELDS = ("enabled", "schedule_minutes", "rate_limit_per_minute", "config")


async def update_source(
    session: AsyncSession, *, actor: User, key: str, changes: dict[str, Any], meta: RequestMeta
) -> JobSource:
    source = await get_source(session, key)
    if changes.get("config") is not None:
        try:
            changes["config"] = get_plugin(source.key).validate_config(changes["config"])
        except ValueError as exc:
            raise AppError(str(exc), code="invalid_source_config") from exc
    before = {f: getattr(source, f) for f in _SOURCE_FIELDS}
    for name, value in changes.items():
        if name in _SOURCE_FIELDS and value is not None:
            setattr(source, name, value)
    after = {f: getattr(source, f) for f in _SOURCE_FIELDS}
    if before != after:
        await audit.record(
            session,
            actor=actor,
            action="job_source.updated",
            target_type="job_source",
            target_id=key,
            before=before,
            after=after,
            meta=meta,
        )
    await session.flush()
    return source


async def list_runs(session: AsyncSession, key: str, limit: int = 20) -> list[IngestionRun]:
    source = await get_source(session, key)
    rows = await session.scalars(
        select(IngestionRun)
        .where(IngestionRun.source_id == source.id)
        .order_by(IngestionRun.started_at.desc())
        .limit(limit)
    )
    return list(rows)


# ------------------------------------------------------------------ admin: companies


async def list_companies(
    session: AsyncSession, *, search: str | None, ats: str | None
) -> list[Company]:
    stmt = select(Company).order_by(Company.name)
    if search:
        stmt = stmt.where(func.lower(Company.name).like(f"%{search.lower()}%"))
    if ats:
        stmt = stmt.where(Company.ats == ats)
    return list(await session.scalars(stmt))


async def set_company_enabled(
    session: AsyncSession, *, actor: User, company_id: uuid.UUID, enabled: bool, meta: RequestMeta
) -> Company:
    company = await session.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found")
    if company.enabled != enabled:
        company.enabled = enabled
        await audit.record(
            session,
            actor=actor,
            action="company.enabled" if enabled else "company.disabled",
            target_type="company",
            target_id=company.id,
            after={"name": company.name, "enabled": enabled},
            meta=meta,
        )
    await session.flush()
    return company


async def delete_company(
    session: AsyncSession, *, actor: User, company_id: uuid.UUID, meta: RequestMeta
) -> list[uuid.UUID]:
    """Remove a company from ingestion; its jobs are retired (and leave the index)."""
    company = await session.get(Company, company_id)
    if company is None:
        raise NotFoundError("Company not found")
    retired = list(
        await session.scalars(
            select(Job.id).where(Job.company_id == company.id, Job.is_active.is_(True))
        )
    )
    for job in await session.scalars(select(Job).where(Job.id.in_(retired))):
        job.is_active = False
    await audit.record(
        session,
        actor=actor,
        action="company.deleted",
        target_type="company",
        target_id=company.id,
        before={"name": company.name, "ats": company.ats.value, "board_token": company.board_token},
        after={"jobs_retired": len(retired)},
        meta=meta,
    )
    await session.delete(company)
    await session.flush()
    return retired


# ------------------------------------------------------------------ admin: jobs


def _admin_job_filter(stmt: Select[Any], search: str | None, status: str | None) -> Select[Any]:
    if search:
        like = f"%{search.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Job.title).like(like), func.lower(Job.company_name).like(like))
        )
    if status == "listed":
        stmt = stmt.where(
            Job.is_active.is_(True), Job.is_hidden.is_(False), Job.duplicate_of_id.is_(None)
        )
    elif status == "hidden":
        stmt = stmt.where(Job.is_hidden.is_(True))
    elif status == "featured":
        stmt = stmt.where(Job.is_featured.is_(True))
    elif status == "inactive":
        stmt = stmt.where(Job.is_active.is_(False))
    elif status == "duplicate":
        stmt = stmt.where(Job.duplicate_of_id.is_not(None))
    return stmt


async def admin_list_jobs(
    session: AsyncSession, *, search: str | None, status: str | None, page: int, page_size: int
) -> tuple[list[Job], int]:
    base = _admin_job_filter(select(Job), search, status)
    total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = await session.scalars(
        base.order_by(Job.first_seen_at.desc(), Job.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def set_job_flags(
    session: AsyncSession,
    *,
    actor: User,
    job_id: uuid.UUID,
    hidden: bool | None,
    featured: bool | None,
    meta: RequestMeta,
) -> Job:
    job = await get_job(session, job_id, include_unlisted=True)
    before = {"hidden": job.is_hidden, "featured": job.is_featured}
    if hidden is not None:
        job.is_hidden = hidden
    if featured is not None:
        job.is_featured = featured
    after = {"hidden": job.is_hidden, "featured": job.is_featured}
    if before != after:
        await audit.record(
            session,
            actor=actor,
            action="job.flags_changed",
            target_type="job",
            target_id=job.id,
            before=before,
            after={**after, "title": job.title, "company": job.company_name},
            meta=meta,
        )
    await session.flush()
    return job


async def mark_not_duplicate(
    session: AsyncSession, *, actor: User, job_id: uuid.UUID, meta: RequestMeta
) -> Job:
    job = await get_job(session, job_id, include_unlisted=True)
    if job.duplicate_of_id is None:
        raise ConflictError("This job is not marked as a duplicate", code="not_duplicate")
    before = {"duplicate_of_id": str(job.duplicate_of_id)}
    job.duplicate_of_id = None
    job.dedup_override = True
    await audit.record(
        session,
        actor=actor,
        action="job.not_duplicate",
        target_type="job",
        target_id=job.id,
        before=before,
        after={"duplicate_of_id": None},
        meta=meta,
    )
    await session.flush()
    return job
