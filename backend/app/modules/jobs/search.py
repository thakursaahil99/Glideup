"""Job search behind one interface, with graceful degradation.

- `MeiliSearchBackend`: typo-tolerant full-text search, filters and facet counts.
- `DatabaseSearchBackend`: plain SQL. Used in tests, when SEARCH_BACKEND=database, and
  automatically whenever Meilisearch is unreachable — search gets simpler, never broken.

The index only returns job ids; jobs are always loaded from Postgres (the source of truth),
so a slightly stale index can never show a hidden or deleted job.
"""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

import structlog
from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.models.settings import Faceting, MeilisearchSettings, Pagination
from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import Job
from app.jobsources.geo import CITY_ALIASES, location_terms, location_variants

logger = structlog.stdlib.get_logger(__name__)

Sort = Literal["relevance", "newest"]
FACETS = ("work_mode", "experience_level", "skills", "company")
MAX_RESULTS = 5000


@dataclass(frozen=True, slots=True)
class SearchQuery:
    q: str = ""
    location: str | None = None
    work_modes: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    companies: tuple[str, ...] = ()
    posted_within_days: int | None = None
    sort: Sort = "relevance"
    offset: int = 0
    limit: int = 20


@dataclass(slots=True)
class SearchHits:
    ids: list[uuid.UUID]
    total: int
    backend: str
    facets: dict[str, dict[str, int]] = field(default_factory=dict)
    took_ms: int = 0


class SearchBackend(Protocol):
    name: str

    async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits: ...
    async def upsert(self, jobs: list[Job]) -> None: ...
    async def delete(self, ids: list[uuid.UUID]) -> None: ...


def to_document(job: Job) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "title": job.title,
        "company": job.company_name,
        "location": job.location or "",
        "location_terms": location_terms(job.location),
        "country": (job.country or "").lower(),
        "work_mode": job.work_mode.value,
        "experience_level": job.experience_level.value,
        "skills": job.skills,
        "department": job.department or "",
        "employment_type": job.employment_type or "",
        "posted_ts": int((job.posted_at or job.first_seen_at).timestamp()),
        "featured": job.is_featured,
        "description": job.description_text[:4000],
    }


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class MeiliSearchBackend:
    name = "meilisearch"

    def __init__(self, settings: Settings):
        key = settings.meili_master_key.get_secret_value() if settings.meili_master_key else None
        self._client = AsyncClient(settings.meili_url, key, timeout=5)
        self._index_name = settings.meili_jobs_index
        self._ready = False

    async def ensure_index(self) -> None:
        if self._ready:
            return
        index = await self._client.get_or_create_index(self._index_name, primary_key="id")
        task = await index.update_settings(
            MeilisearchSettings(
                searchable_attributes=[
                    "title", "skills", "company", "department", "location", "description",
                ],
                filterable_attributes=[
                    "work_mode", "experience_level", "skills", "company",
                    "location_terms", "country", "posted_ts", "featured",
                ],
                sortable_attributes=["posted_ts", "featured"],
                ranking_rules=["words", "typo", "proximity", "attribute", "sort", "exactness"],
                faceting=Faceting(max_values_per_facet=40),
                pagination=Pagination(max_total_hits=MAX_RESULTS),
            )
        )  # fmt: skip
        await self._client.wait_for_task(task.task_uid, timeout_in_ms=30_000)
        self._ready = True

    def _filters(self, query: SearchQuery) -> list[str | list[str]]:
        filters: list[str | list[str]] = []
        if query.work_modes:
            filters.append([f"work_mode = {_quote(m)}" for m in query.work_modes])
        if query.levels:
            filters.append([f"experience_level = {_quote(lv)}" for lv in query.levels])
        if query.companies:
            filters.append([f"company = {_quote(c)}" for c in query.companies])
        filters.extend(f"skills = {_quote(s)}" for s in query.skills)  # every skill required
        if query.location:
            term = " ".join(query.location.lower().split())
            filters.append(f"location_terms = {_quote(CITY_ALIASES.get(term, term))}")
        if query.posted_within_days:
            since = datetime.now(UTC) - timedelta(days=query.posted_within_days)
            filters.append(f"posted_ts >= {int(since.timestamp())}")
        return filters

    async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits:
        await self.ensure_index()
        started = time.perf_counter()
        sort = (
            ["featured:desc", "posted_ts:desc"] if query.sort == "newest" or not query.q else None
        )
        result = await self._client.index(self._index_name).search(
            query.q or None,
            offset=query.offset,
            limit=query.limit,
            filter=self._filters(query) or None,
            facets=list(FACETS),
            sort=sort,
            attributes_to_retrieve=["id"],
            matching_strategy="all",
        )
        return SearchHits(
            ids=[uuid.UUID(hit["id"]) for hit in result.hits],
            total=result.estimated_total_hits or 0,
            backend=self.name,
            facets={k: dict(v) for k, v in (result.facet_distribution or {}).items()},
            took_ms=int((time.perf_counter() - started) * 1000),
        )

    async def upsert(self, jobs: list[Job]) -> None:
        if not jobs:
            return
        await self.ensure_index()
        index = self._client.index(self._index_name)
        for start in range(0, len(jobs), 1000):
            await index.add_documents([to_document(j) for j in jobs[start : start + 1000]])

    async def delete(self, ids: list[uuid.UUID]) -> None:
        if ids:
            await self.ensure_index()
            await self._client.index(self._index_name).delete_documents([str(i) for i in ids])

    async def clear(self) -> None:
        await self.ensure_index()
        task = await self._client.index(self._index_name).delete_all_documents()
        await self._client.wait_for_task(task.task_uid, timeout_in_ms=60_000)


def listed() -> Any:
    return and_(Job.is_active.is_(True), Job.is_hidden.is_(False), Job.duplicate_of_id.is_(None))


class DatabaseSearchBackend:
    """Degraded-mode search: titles, companies and skills only (no full text, no typos)."""

    name = "database"

    def _apply_filters[*Ts](self, stmt: Select[*Ts], query: SearchQuery) -> Select[*Ts]:
        stmt = stmt.where(listed())
        for term in query.q.lower().split()[:8]:
            like = f"%{term}%"
            stmt = stmt.where(
                or_(
                    func.lower(Job.title).like(like),
                    func.lower(Job.company_name).like(like),
                    Job.skills_index.like(f"%|{term}%"),
                    # No description scan: this is the degraded mode and must stay fast.
                )
            )
        if query.work_modes:
            stmt = stmt.where(Job.work_mode.in_(query.work_modes))
        if query.levels:
            stmt = stmt.where(Job.experience_level.in_(query.levels))
        if query.companies:
            stmt = stmt.where(Job.company_name.in_(query.companies))
        for skill in query.skills:
            stmt = stmt.where(Job.skills_index.like(f"%|{skill.lower()}|%"))
        if query.location:
            names = location_variants(query.location)
            stmt = stmt.where(or_(*(func.lower(Job.location).like(f"%{n}%") for n in names)))
        if query.posted_within_days:
            since = datetime.now(UTC) - timedelta(days=query.posted_within_days)
            stmt = stmt.where(func.coalesce(Job.posted_at, Job.first_seen_at) >= since)
        return stmt

    async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits:
        started = time.perf_counter()
        base = self._apply_filters(select(Job.id), query)
        total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
        order: list[Any] = [Job.is_featured.desc()]
        if query.q and query.sort == "relevance":
            order.append(case((func.lower(Job.title).like(f"%{query.q.lower()}%"), 0), else_=1))
        order += [func.coalesce(Job.posted_at, Job.first_seen_at).desc(), Job.id]
        ids = list(
            await session.scalars(base.order_by(*order).offset(query.offset).limit(query.limit))
        )

        facets: dict[str, dict[str, int]] = {}
        for name, column in (
            ("work_mode", Job.work_mode),
            ("experience_level", Job.experience_level),
            ("company", Job.company_name),
        ):
            rows = await session.execute(
                self._apply_filters(select(column, func.count()), query)
                .group_by(column)
                .order_by(func.count().desc())
                .limit(40)
            )
            facets[name] = {str(getattr(k, "value", k)): int(n) for k, n in rows.all()}
        return SearchHits(
            ids=ids,
            total=min(total, MAX_RESULTS),
            backend=self.name,
            facets=facets,
            took_ms=int((time.perf_counter() - started) * 1000),
        )

    async def upsert(self, jobs: list[Job]) -> None:
        return None  # the database is the index

    async def delete(self, ids: list[uuid.UUID]) -> None:
        return None


class ResilientSearch:
    """Meilisearch first; if it fails, answer from the database and say so."""

    def __init__(self, primary: SearchBackend, fallback: DatabaseSearchBackend):
        self.primary = primary
        self.fallback = fallback
        self.name = primary.name

    async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits:
        try:
            return await self.primary.search(session, query)
        except Exception as exc:
            logger.warning("search_fallback", backend=self.primary.name, error=type(exc).__name__)
            return await self.fallback.search(session, query)

    async def upsert(self, jobs: list[Job]) -> None:
        await self.primary.upsert(jobs)

    async def delete(self, ids: list[uuid.UUID]) -> None:
        await self.primary.delete(ids)


_search: SearchBackend | None = None


def get_search() -> SearchBackend:
    global _search
    if _search is None:
        settings = get_settings()
        database = DatabaseSearchBackend()
        _search = (
            ResilientSearch(MeiliSearchBackend(settings), database)
            if settings.search_backend == "meilisearch"
            else database
        )
    return _search


def set_search(backend: SearchBackend | None) -> None:
    global _search
    _search = backend
