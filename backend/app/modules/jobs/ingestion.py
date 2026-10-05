"""Ingestion pipeline: fetch -> normalise -> upsert -> dedup -> stale -> index.

Runs per source, as a background job (Celery Beat every few minutes picks sources whose
schedule is due; admins can also "Run now"). Each scope (board or query) is committed on
its own, so a long run makes visible progress and a crash loses at most one scope.
"""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import and_, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ATS, Company, IngestionRun, Job, JobSource, RunStatus
from app.db.session import session_factory
from app.jobsources.base import BoardTarget, FetchContext, Posting, ScopeResult
from app.jobsources.geo import location_index
from app.jobsources.http import SourceHttpClient
from app.jobsources.normalize import NormalizedJob, normalize, posting_hash
from app.jobsources.registry import get_plugin
from app.modules.jobs.search import get_search, listed
from app.workers.runtime import dispatch

logger = structlog.stdlib.get_logger(__name__)

RUN_LOCK_TIMEOUT = timedelta(hours=1)
MAX_ERRORS_KEPT = 50


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_due(source: JobSource, now: datetime | None = None) -> bool:
    if not source.enabled:
        return False
    if source.last_run_at is None:
        return True
    return _aware(source.last_run_at) + timedelta(minutes=source.schedule_minutes) <= (
        now or _now()
    )


def _apply(job: Job, item: NormalizedJob) -> None:
    p = item.posting
    job.title = item.title
    job.company_name = " ".join(p.company_name.split())[:200]
    job.location = (p.location or None) and p.location[:300]
    geo = item.geo
    job.country = geo.countries[0] if geo.countries else None
    job.countries = geo.countries
    job.states = [s[:100] for s in geo.states]
    job.cities = [c[:100] for c in geo.cities]
    job.remote_scope = item.remote_scope
    job.location_index = location_index(geo)
    job.work_mode = item.work_mode
    job.experience_level = item.experience_level
    job.employment_type = p.employment_type
    job.department = p.department[:200] if p.department else None
    job.description_html = item.description_html
    job.description_text = item.description_text
    job.apply_url = p.apply_url[:1000]
    job.salary_min = p.salary_min
    job.salary_max = p.salary_max
    job.salary_currency = (p.salary_currency or None) and p.salary_currency[:3].upper()
    job.salary_period = p.salary_period
    job.skills = item.skills
    job.skills_index = "|" + "|".join(s.lower() for s in item.skills) + "|" if item.skills else ""
    job.posted_at = p.posted_at
    job.content_hash = item.content_hash
    job.dedup_hash = item.dedup_hash


async def _apply_scope(
    session: AsyncSession, source: JobSource, run: IngestionRun, result: ScopeResult
) -> set[uuid.UUID]:
    """Upsert one scope's postings and retire the ones that disappeared. Returns touched ids."""
    now = _now()
    items: dict[str, Posting] = {}
    for posting in result.postings:
        if (
            posting.title
            and posting.apply_url
            and posting.apply_url.startswith(("http://", "https://"))
        ):
            items[posting.external_id] = posting

    existing = {
        job.external_id: job
        for job in await session.scalars(
            select(Job).where(
                Job.source_id == source.id,
                (Job.scope == result.scope) | Job.external_id.in_(list(items)),
            )
        )
    }
    touched: set[uuid.UUID] = set()
    fresh: list[Job] = []

    for external_id, posting in items.items():
        job = existing.get(external_id)
        if posting.details_omitted:
            # The source says it hasn't changed since our copy: just keep it listed.
            if job is not None:
                job.last_seen_at = now
                if not job.is_active:
                    job.is_active = True
                    fresh.append(job)
            continue
        if job is None:
            job = Job(
                source_id=source.id,
                company_id=result.company_id,
                external_id=external_id,
                scope=result.scope,
                first_seen_at=now,
            )
            _apply(job, normalize(posting))
            session.add(job)
            fresh.append(job)
            run.created += 1
        elif (
            # Unchanged postings (most of them, every run) skip normalisation entirely.
            job.content_hash != posting_hash(posting)
            or not job.is_active
            or job.scope != result.scope
        ):
            _apply(job, normalize(posting))
            job.scope = result.scope
            job.is_active = True
            fresh.append(job)
            run.updated += 1
        job.last_seen_at = now
        if job.company_id is None:
            job.company_id = result.company_id

    # Stale: jobs this scope listed before but not any more.
    for external_id, job in existing.items():
        if external_id not in items and job.is_active and job.scope == result.scope:
            job.is_active = False
            touched.add(job.id)
            run.deactivated += 1
            # Promote its duplicates: they become the listed copy now.
            for dup in await session.scalars(select(Job).where(Job.duplicate_of_id == job.id)):
                dup.duplicate_of_id = None
                touched.add(dup.id)

    await session.flush()
    run.duplicates += await _mark_duplicates(session, fresh)
    touched.update(job.id for job in fresh)
    return touched


async def _mark_duplicates(session: AsyncSession, jobs: Iterable[Job]) -> int:
    """A job is a duplicate if an older, listed job has the same title+company+location."""
    marked = 0
    for job in jobs:
        if job.dedup_override or not job.is_active:
            continue
        canonical = await session.scalar(
            select(Job.id)
            .where(
                Job.dedup_hash == job.dedup_hash,
                Job.id != job.id,
                # Strictly "older" (ties broken by id) so two copies never point at each other.
                or_(
                    Job.first_seen_at < job.first_seen_at,
                    and_(Job.first_seen_at == job.first_seen_at, Job.id < job.id),
                ),
                listed(),
            )
            .order_by(Job.first_seen_at, Job.id)
            .limit(1)
        )
        if job.duplicate_of_id != canonical:
            job.duplicate_of_id = canonical
            marked += int(canonical is not None)
    return marked


async def _refresh_counts(session: AsyncSession, source: JobSource) -> None:
    source.active_jobs = (
        await session.scalar(
            select(func.count()).where(Job.source_id == source.id, Job.is_active.is_(True))
        )
        or 0
    )
    rows = await session.execute(
        select(Job.company_id, func.count())
        .where(Job.source_id == source.id, Job.is_active.is_(True), Job.company_id.is_not(None))
        .group_by(Job.company_id)
    )
    counts = dict(rows.all())
    if source.key in ATS._value2member_map_:
        await session.execute(
            update(Company).where(Company.ats == ATS(source.key)).values(active_jobs=0)
        )
    for company_id, count in counts.items():
        company = await session.get(Company, company_id)
        if company is not None:
            company.active_jobs = count


async def ingest_source(
    source_key: str, *, trigger: str = "schedule", actor_id: str | None = None
) -> str | None:
    """Run one source end to end. Returns the run id, or None if skipped."""
    touched: set[uuid.UUID] = set()
    async with session_factory()() as session:
        source = await session.scalar(select(JobSource).where(JobSource.key == source_key))
        if source is None or (trigger == "schedule" and not source.enabled):
            return None
        running = await session.scalar(
            select(IngestionRun.id).where(
                IngestionRun.source_id == source.id,
                IngestionRun.status == RunStatus.RUNNING,
                IngestionRun.started_at > _now() - RUN_LOCK_TIMEOUT,
            )
        )
        if running is not None:
            logger.info("ingestion_skipped_already_running", source=source_key)
            return None

        plugin = get_plugin(source.key)
        run = IngestionRun(
            source_id=source.id,
            trigger=trigger,
            triggered_by_id=uuid.UUID(actor_id) if actor_id else None,
            status=RunStatus.RUNNING,
            started_at=_now(),
            errors=[],
        )
        session.add(run)
        source.last_run_at = _now()
        not_ready = plugin.is_configured(source.config)
        if not_ready:
            run.status, run.finished_at, run.errors = RunStatus.FAILED, _now(), [not_ready]
            source.last_error = not_ready
            await session.commit()
            return str(run.id)
        await session.commit()

        boards: list[BoardTarget] = []
        companies: dict[str, Company] = {}
        if plugin.uses_company_boards:
            for company in await session.scalars(
                select(Company).where(Company.ats == ATS(source.key), Company.enabled.is_(True))
            ):
                boards.append(BoardTarget(company.id, company.name, company.board_token))
                companies[f"{source.key}:{company.board_token}"] = company

        known = {
            external_id: int(posted_at.replace(tzinfo=posted_at.tzinfo or UTC).timestamp())
            for external_id, posted_at in await session.execute(
                select(Job.external_id, Job.posted_at).where(
                    Job.source_id == source.id, Job.posted_at.is_not(None)
                )
            )
            if posted_at is not None
        }
        http = SourceHttpClient(rate_limit_per_minute=source.rate_limit_per_minute)
        errors: list[str] = []
        scopes_ok = 0
        log = logger.bind(source=source_key, run_id=str(run.id))
        try:
            async for result in plugin.fetch(
                FetchContext(http, source.config or {}, boards, known=known)
            ):
                run.fetched += len(result.postings)
                board_company = companies.get(result.scope)
                if not result.complete:
                    errors.append(f"{result.scope}: {result.error}")
                    if board_company is not None:
                        board_company.last_error = result.error
                    await session.commit()
                    continue
                touched |= await _apply_scope(session, source, run, result)
                if board_company is not None:
                    board_company.last_fetched_at, board_company.last_error = _now(), None
                scopes_ok += 1
                await session.commit()
        except Exception as exc:  # a bug in a plugin must not leave the run "running" forever
            log.exception("ingestion_crashed")
            errors.append(f"crashed: {type(exc).__name__}: {exc}"[:500])
            await session.rollback()
            run = await session.get(IngestionRun, run.id) or run
            source = await session.get(JobSource, source.id) or source
        finally:
            await http.aclose()

        failed = bool(errors) and scopes_ok == 0
        run.status = (
            RunStatus.FAILED if failed else RunStatus.PARTIAL if errors else RunStatus.SUCCESS
        )
        run.errors = errors[:MAX_ERRORS_KEPT]
        run.finished_at = _now()
        source.last_error = errors[0] if errors else None
        source.consecutive_failures = source.consecutive_failures + 1 if failed else 0
        if not failed:
            source.last_success_at = _now()
        await _refresh_counts(session, source)
        await session.commit()
        log.info(
            "ingestion_finished",
            status=run.status.value,
            fetched=run.fetched,
            created=run.created,
            updated=run.updated,
            deactivated=run.deactivated,
            duplicates=run.duplicates,
            errors=len(errors),
        )
        run_id = str(run.id)

    touched |= await refresh_company_hiring()
    await sync_search(touched)
    if run_id is not None:
        _queue_embeddings()
    return run_id


def _queue_embeddings() -> None:
    """New and changed jobs need vectors for matching; the backfill only touches those."""
    from app.modules.matching import embeddings, tasks

    dispatch(tasks.embed_jobs, embeddings.embed_jobs_job)


HIRING_WINDOW = timedelta(days=7)


async def refresh_company_hiring() -> set[uuid.UUID]:
    """Recount open roles (and roles posted in the last 7 days) per company and store them
    on every listed job, so search can sort by "most hiring" and show a hiring badge.
    Returns the ids whose numbers changed (they need re-indexing)."""
    since = _now() - HIRING_WINDOW
    changed: set[uuid.UUID] = set()
    async with session_factory()() as session:
        posted = func.coalesce(Job.posted_at, Job.first_seen_at)
        rows = await session.execute(
            select(
                Job.company_name,
                func.count(),
                func.coalesce(func.sum(case((posted >= since, 1), else_=0)), 0),
            )
            .where(listed())
            .group_by(Job.company_name)
        )
        for company, open_roles, new_roles in rows.all():
            result = await session.execute(
                update(Job)
                .where(
                    Job.company_name == company,
                    listed(),
                    or_(
                        Job.company_open_roles != open_roles,
                        Job.company_new_roles_7d != int(new_roles),
                    ),
                )
                .values(company_open_roles=open_roles, company_new_roles_7d=int(new_roles))
                .returning(Job.id)
            )
            changed.update(result.scalars())
        await session.commit()
    return changed


async def run_ingestion(
    source_key: str, trigger: str = "schedule", actor_id: str | None = None
) -> str | None:
    """Positional-argument entry point shared by Celery and inline dispatch, so both
    receive the arguments in the same order."""
    return await ingest_source(source_key, trigger=trigger, actor_id=actor_id)


async def sync_search(ids: Iterable[uuid.UUID]) -> None:
    """Push listed jobs to the search index and remove everything else. Best effort: a
    failure is logged and fixed by the next sync or an admin "rebuild index"."""
    ids = list(ids)
    if not ids:
        return
    search = get_search()
    try:
        async with session_factory()() as session:
            for start in range(0, len(ids), 1000):
                jobs = list(
                    await session.scalars(select(Job).where(Job.id.in_(ids[start : start + 1000])))
                )
                await search.upsert([j for j in jobs if j.is_listed])
                await search.delete([j.id for j in jobs if not j.is_listed])
    except Exception as exc:
        logger.warning("search_sync_failed", error=type(exc).__name__, jobs=len(ids))


async def rebuild_search_index() -> int:
    search = get_search()
    primary = getattr(search, "primary", search)
    if hasattr(primary, "clear"):
        await primary.clear()
    count = 0
    async with session_factory()() as session:
        last_id: uuid.UUID | None = None
        while True:
            stmt = select(Job).where(listed()).order_by(Job.id).limit(1000)
            if last_id is not None:
                stmt = stmt.where(Job.id > last_id)
            batch = list(await session.scalars(stmt))
            if not batch:
                break
            await search.upsert(batch)
            count += len(batch)
            last_id = batch[-1].id
    return count


async def ingest_due_sources() -> list[str]:
    """Called by Celery Beat (or the inline scheduler): start every source whose time has come."""
    from app.modules.jobs import tasks  # local import: tasks imports this module
    from app.workers.runtime import dispatch

    async with session_factory()() as session:
        sources = [s for s in await session.scalars(select(JobSource)) if is_due(s)]
    for source in sources:
        dispatch(tasks.ingest_source_task, run_ingestion, source.key, "schedule")
    return [s.key for s in sources]


def salary_text(job: Job) -> str | None:
    if job.salary_min is None and job.salary_max is None:
        return None

    def fmt(value: Decimal | None) -> str:
        return f"{int(value):,}" if value is not None else "?"

    period = f"/{job.salary_period}" if job.salary_period else ""
    salary_range = f"{fmt(job.salary_min)}\u2013{fmt(job.salary_max)}{period}"
    return f"{job.salary_currency or ''} {salary_range}".strip()
