"""Job search behind one interface, with graceful degradation.

- `MeiliSearchBackend`: typo-tolerant full-text search, filters and facet counts.
- `DatabaseSearchBackend`: plain SQL. Used in tests, when SEARCH_BACKEND=database, and
  automatically whenever Meilisearch is unreachable — search gets simpler, never broken.

The index only returns job ids; jobs are always loaded from Postgres (the source of truth),
so a slightly stale index can never show a hidden or deleted job.

Location facets are *disjunctive*: the country counts ignore the selected country, the state
counts ignore the selected state, and so on, so a dropdown always shows every option with
an honest count instead of collapsing to the one already chosen.
"""

import time
import uuid
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, Protocol

import structlog
from meilisearch_python_sdk import AsyncClient
from meilisearch_python_sdk.models.search import SearchParams
from meilisearch_python_sdk.models.settings import Faceting, MeilisearchSettings, Pagination
from sqlalchemy import Select, and_, case, func, not_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import Job
from app.jobsources.geo import (
    city_place,
    location_variants,
    lookup_metro,
    metro_cities,
    metro_country,
    parse_location,
    state_countries,
)
from app.jobsources.geo_data import METROS

logger = structlog.stdlib.get_logger(__name__)

Sort = Literal["relevance", "newest", "hiring"]
RemoteFilter = Literal["india", "worldwide"]
Region = Literal["india", "international"]
FACETS = ("work_mode", "experience_level", "skills", "company", "countries", "states", "cities")
MAX_RESULTS = 5000
INDIA = "IN"


@dataclass(frozen=True, slots=True)
class SearchQuery:
    q: str = ""
    location: str | None = None  # free text (older clients); resolved to a structured filter
    countries: tuple[str, ...] = ()
    states: tuple[str, ...] = ()
    cities: tuple[str, ...] = ()
    metros: tuple[str, ...] = ()  # e.g. "Delhi NCR": expands to its member cities
    remote: RemoteFilter | None = None
    region: Region | None = None
    work_modes: tuple[str, ...] = ()
    levels: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    companies: tuple[str, ...] = ()
    posted_within_days: int | None = None
    sort: Sort = "relevance"
    offset: int = 0
    limit: int = 20

    def resolved(self) -> "SearchQuery":
        """Expand metros into cities, and turn free-text `location` into structured filters
        when it can be recognised."""
        if self.metros:
            cities = dict.fromkeys(self.cities)
            for metro in self.metros:
                cities.update(dict.fromkeys(metro_cities(metro)))
            return replace(self, metros=(), cities=tuple(cities)).resolved()
        if self.location and (found := lookup_metro(self.location)):
            return replace(self, location=None, metros=(found,)).resolved()
        if not self.location or self.countries or self.states or self.cities:
            return self
        places = parse_location(self.location).places
        if len(places) != 1:
            return self
        place = places[0]
        if place.city:
            return replace(self, location=None, cities=(place.city,))
        if place.state:
            return replace(self, location=None, states=(place.state,))
        if place.country:
            return replace(self, location=None, countries=(place.country,))
        return self


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
        "countries": job.countries,
        "states": job.states,
        "cities": job.cities,
        "remote_scope": job.remote_scope or "",
        "work_mode": job.work_mode.value,
        "experience_level": job.experience_level.value,
        "skills": job.skills,
        "department": job.department or "",
        "employment_type": job.employment_type or "",
        "posted_ts": int((job.posted_at or job.first_seen_at).timestamp()),
        "featured": job.is_featured,
        "company_open_roles": job.company_open_roles,
        "description": job.description_text[:4000],
    }


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


# The facets whose own filter is dropped when computing their counts (see module docstring).
def scope_location_facets(query: SearchQuery, facets: dict[str, dict[str, int]]) -> None:
    """A job listed in "Bengaluru; Seattle" matches India, but "Washington" must not appear
    in India's state list. Keep states/cities that belong to the selection (or are unknown
    to the gazetteer, so nothing is ever silently hidden)."""
    countries, states = set(query.countries), set(query.states)
    if query.region == "india" or query.remote == "india":
        countries.add(INDIA)
    if countries and "states" in facets:
        facets["states"] = {
            s: n
            for s, n in facets["states"].items()
            if not (owners := state_countries(s)) or owners & countries
        }
    if (countries or states) and "cities" in facets:
        kept = {}
        for city, n in facets["cities"].items():
            place = city_place(city)
            if place is None or (
                (not countries or place[0] in countries) and (not states or place[1] in states)
            ):
                kept[city] = n
        facets["cities"] = kept


def relevant_metros(query: SearchQuery) -> list[str]:
    """Metros worth counting for this query: those in the selected country (or all)."""
    countries = set(query.countries)
    if query.region == "india" or query.remote == "india":
        countries.add(INDIA)
    if query.region == "international":
        return [m for m in METROS if metro_country(m) != INDIA]
    return [m for m in METROS if not countries or metro_country(m) in countries]


# State and city depend on country, so each level ignores its own and deeper selections.
_DISJUNCTIVE = {
    "countries": {"countries", "states", "cities"},
    "states": {"states", "cities"},
    "cities": {"cities"},
}


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
                    "title", "skills", "company", "department", "location", "cities",
                    "states", "description",
                ],
                filterable_attributes=[
                    "work_mode", "experience_level", "skills", "company", "countries",
                    "states", "cities", "remote_scope", "posted_ts", "featured",
                ],
                sortable_attributes=["posted_ts", "featured", "company_open_roles"],
                ranking_rules=["words", "typo", "proximity", "attribute", "sort", "exactness"],
                # Count order, so the biggest employers are never cut off alphabetically.
                faceting=Faceting(max_values_per_facet=100, sort_facet_values_by={"*": "count"}),
                pagination=Pagination(max_total_hits=MAX_RESULTS),
            )
        )  # fmt: skip
        await self._client.wait_for_task(task.task_uid, timeout_in_ms=30_000)
        self._ready = True

    def _filters(
        self, query: SearchQuery, *, skip: set[str] | frozenset[str] = frozenset()
    ) -> list[Any]:
        filters: list[Any] = []

        def any_of(attr: str, values: tuple[str, ...]) -> None:
            if values and attr not in skip:
                filters.append([f"{attr} = {_quote(v)}" for v in values])

        any_of("work_mode", query.work_modes)
        any_of("experience_level", query.levels)
        any_of("company", query.companies)
        any_of("countries", query.countries)
        any_of("states", query.states)
        any_of("cities", query.cities)
        filters.extend(f"skills = {_quote(s)}" for s in query.skills)  # every skill required
        if query.region == "india":
            filters.append(f"countries = {_quote(INDIA)}")
        elif query.region == "international":
            filters.append(f"NOT countries = {_quote(INDIA)}")
        if query.remote == "india":
            filters.append(f'work_mode = "remote" AND countries = {_quote(INDIA)}')
        elif query.remote == "worldwide":
            filters.append('remote_scope = "worldwide"')
        if query.posted_within_days:
            since = datetime.now(UTC) - timedelta(days=query.posted_within_days)
            filters.append(f"posted_ts >= {int(since.timestamp())}")
        return filters

    async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits:
        await self.ensure_index()
        started = time.perf_counter()
        query = query.resolved()
        if query.sort == "hiring":
            sort: list[str] | None = ["featured:desc", "company_open_roles:desc", "posted_ts:desc"]
        elif query.sort == "newest" or not query.q:
            sort = ["featured:desc", "posted_ts:desc"]
        else:
            sort = None
        common: dict[str, Any] = {"query": query.q or None, "matching_strategy": "all"}
        main = SearchParams(
            index_uid=self._index_name,
            offset=query.offset,
            limit=query.limit,
            filter=self._filters(query) or None,
            facets=list(FACETS),
            sort=sort,
            attributes_to_retrieve=["id"],
            **common,
        )
        # One extra facet-only query per active location filter (disjunctive counts).
        extra = [
            (facet, skip)
            for facet, skip in _DISJUNCTIVE.items()
            if any(getattr(query, attr) for attr in skip)
        ]
        metros = relevant_metros(query)
        params = [main] + [
            SearchParams(
                index_uid=self._index_name,
                limit=0,
                filter=self._filters(query, skip=skip) or None,
                facets=[facet],
                **common,
            )
            for facet, skip in extra
        ]
        for metro in metros:  # exact count per metro (a job in two NCR cities counts once)
            members = [f"cities = {_quote(c)}" for c in metro_cities(metro)]
            params.append(
                SearchParams(
                    index_uid=self._index_name,
                    limit=0,
                    filter=[*self._filters(query, skip={"states", "cities"}), members],
                    **common,
                )
            )
        results = await self._client.multi_search(params)
        if not isinstance(results, list):  # only federated searches return a single object
            raise TypeError("Unexpected federated multi-search response")
        first = results[0]
        facets = {k: dict(v) for k, v in (first.facet_distribution or {}).items()}
        for (facet, _), result in zip(extra, results[1 : 1 + len(extra)], strict=True):
            facets[facet] = dict((result.facet_distribution or {}).get(facet, {}))
        facets["metros"] = {
            metro: result.estimated_total_hits or 0
            for metro, result in zip(metros, results[1 + len(extra) :], strict=True)
        }
        scope_location_facets(query, facets)
        return SearchHits(
            ids=[uuid.UUID(hit["id"]) for hit in first.hits],
            total=first.estimated_total_hits or 0,
            backend=self.name,
            facets=facets,
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


def _index_has(prefix: str, value: str) -> Any:
    return Job.location_index.like(f"%|{prefix}:{value}|%")


class DatabaseSearchBackend:
    """Degraded-mode search: titles, companies and skills only (no full text, no typos)."""

    name = "database"
    FACET_SCAN_LIMIT = 20_000

    def _apply_filters[*Ts](
        self,
        stmt: Select[*Ts],
        query: SearchQuery,
        *,
        skip: set[str] | frozenset[str] = frozenset(),
    ) -> Select[*Ts]:
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
        for attr, prefix in (("countries", "c"), ("states", "s"), ("cities", "ci")):
            values: tuple[str, ...] = getattr(query, attr)
            if values and attr not in skip:
                stmt = stmt.where(or_(*(_index_has(prefix, v) for v in values)))
        if query.region == "india":
            stmt = stmt.where(_index_has("c", INDIA))
        elif query.region == "international":
            stmt = stmt.where(not_(_index_has("c", INDIA)))
        if query.remote == "india":
            stmt = stmt.where(Job.work_mode == "remote", _index_has("c", INDIA))
        elif query.remote == "worldwide":
            stmt = stmt.where(Job.remote_scope == "worldwide")
        if query.location:  # unrecognised free text: match the raw location string
            names = location_variants(query.location)
            stmt = stmt.where(or_(*(func.lower(Job.location).like(f"%{n}%") for n in names)))
        if query.posted_within_days:
            since = datetime.now(UTC) - timedelta(days=query.posted_within_days)
            stmt = stmt.where(func.coalesce(Job.posted_at, Job.first_seen_at) >= since)
        return stmt

    async def _location_facet(
        self, session: AsyncSession, query: SearchQuery, facet: str
    ) -> dict[str, int]:
        column = getattr(Job, facet)
        rows: list[list[str] | None] = list(
            await session.scalars(
                self._apply_filters(select(column), query, skip=_DISJUNCTIVE[facet]).limit(
                    self.FACET_SCAN_LIMIT
                )
            )
        )
        counts: Counter[str] = Counter()
        for values in rows:
            counts.update(values or [])
        return dict(counts.most_common(100))

    async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits:
        started = time.perf_counter()
        query = query.resolved()
        base = self._apply_filters(select(Job.id), query)
        total = await session.scalar(select(func.count()).select_from(base.subquery())) or 0
        order: list[Any] = [Job.is_featured.desc()]
        if query.sort == "hiring":
            order.append(Job.company_open_roles.desc())
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
        for facet in ("countries", "states", "cities"):
            facets[facet] = await self._location_facet(session, query, facet)
        facets["metros"] = {}
        for metro in relevant_metros(query):
            members = replace(query, states=(), cities=metro_cities(metro))
            stmt = self._apply_filters(select(func.count(Job.id)), members)
            facets["metros"][metro] = await session.scalar(stmt) or 0
        scope_location_facets(query, facets)
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
