"""Ingestion pipeline, search and the jobs / admin APIs, driven by a scripted fake source."""

import io
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ATS, AuditLog, Company, IngestionRun, Job, JobSource, RunStatus
from app.jobsources import registry
from app.jobsources.base import FetchContext, Posting, ScopeResult
from app.modules.jobs import catalog
from app.modules.jobs.ingestion import ingest_due_sources, ingest_source, is_due
from app.modules.jobs.search import (
    DatabaseSearchBackend,
    ResilientSearch,
    SearchHits,
    SearchQuery,
    set_search,
)
from app.workers.runtime import drain_inline_jobs
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn


class FakePlugin:
    """Each run yields the scopes in `self.scopes` (a scope of None = that board failed)."""

    key = "fake"
    name = "Fake source"
    uses_company_boards = False
    attribution: str | None = "Jobs by Fake"

    def __init__(self) -> None:
        self.scopes: dict[str, list[Posting] | None] = {}
        self.ready: str | None = None

    def is_configured(self, config: dict[str, Any]) -> str | None:
        return self.ready

    async def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]:
        for scope, postings in self.scopes.items():
            if postings is None:
                yield ScopeResult(scope, complete=False, error="HTTP 503")
            else:
                yield ScopeResult(scope, list(postings))


def posting(
    external_id: str,
    title: str = "Backend Engineer",
    company: str = "Acme",
    location: str = "Bengaluru, India",
    body: str = "<p>Python, FastAPI and PostgreSQL</p>",
    days_ago: int = 1,
) -> Posting:
    return Posting(
        external_id=external_id,
        title=title,
        company_name=company,
        apply_url=f"https://careers.example.com/{external_id}",
        description_html=body,
        location=location,
        posted_at=datetime.now(UTC) - timedelta(days=days_ago),
    )


@pytest.fixture
def fake() -> Iterator[FakePlugin]:
    plugin = FakePlugin()
    registry.PLUGINS["fake"] = plugin
    yield plugin
    registry.PLUGINS.pop("fake", None)


@pytest.fixture
async def fake_source(session: AsyncSession, fake: FakePlugin) -> JobSource:
    source = JobSource(key="fake", name="Fake", config={}, enabled=True)
    session.add(source)
    await session.commit()
    return source


async def jobs_by_ext(session: AsyncSession) -> dict[str, Job]:
    session.expire_all()
    return {j.external_id: j for j in await session.scalars(select(Job))}


async def last_run(session: AsyncSession) -> IngestionRun:
    run = await session.scalar(select(IngestionRun).order_by(IngestionRun.started_at.desc()))
    assert run is not None
    await session.refresh(run)
    return run


# --- ingestion pipeline ---


async def test_first_run_creates_jobs(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.scopes = {"fake:a": [posting("1"), posting("2", title="Senior Frontend Engineer")]}
    assert await ingest_source("fake") is not None
    jobs = await jobs_by_ext(session)
    assert set(jobs) == {"1", "2"}
    assert jobs["2"].experience_level.value == "senior"
    assert "Python" in jobs["1"].skills
    assert jobs["1"].skills_index.startswith("|")
    run = await last_run(session)
    assert (run.status, run.fetched, run.created) == (RunStatus.SUCCESS, 2, 2)
    await session.refresh(fake_source)
    assert fake_source.active_jobs == 2
    assert fake_source.last_success_at is not None


async def test_rerun_updates_changed_and_retires_missing(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.scopes = {"fake:a": [posting("1"), posting("2")]}
    await ingest_source("fake")
    fake.scopes = {"fake:a": [posting("1", body="<p>Now with Rust</p>")]}
    await ingest_source("fake")
    jobs = await jobs_by_ext(session)
    assert "Rust" in jobs["1"].skills
    assert jobs["2"].is_active is False
    run = await last_run(session)
    assert (run.updated, run.deactivated, run.created) == (1, 1, 0)

    # It comes back: reactivated, not duplicated.
    fake.scopes = {"fake:a": [posting("1", body="<p>Now with Rust</p>"), posting("2")]}
    await ingest_source("fake")
    assert (await jobs_by_ext(session))["2"].is_active is True


async def test_failed_scope_keeps_its_jobs(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.scopes = {"fake:a": [posting("1")], "fake:b": [posting("2", company="Beta")]}
    await ingest_source("fake")
    fake.scopes = {"fake:a": [posting("1")], "fake:b": None}  # board b is down
    await ingest_source("fake")
    jobs = await jobs_by_ext(session)
    assert jobs["2"].is_active is True  # not wrongly retired
    run = await last_run(session)
    assert run.status == RunStatus.PARTIAL
    assert run.errors == ["fake:b: HTTP 503"]


async def test_all_scopes_failing_marks_the_run_failed(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.scopes = {"fake:a": None}
    await ingest_source("fake")
    await ingest_source("fake")
    await session.refresh(fake_source)
    assert (await last_run(session)).status == RunStatus.FAILED
    assert fake_source.consecutive_failures == 2
    assert fake_source.last_error == "fake:a: HTTP 503"


async def test_duplicates_across_sources_are_listed_once(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.scopes = {"fake:a": [posting("1", title="Data Engineer", company="Acme")]}
    await ingest_source("fake")
    # The same role shows up again under another id (e.g. from an aggregator).
    fake.scopes = {
        "fake:a": [posting("1", title="Data Engineer", company="Acme")],
        "fake:agg": [posting("agg-9", title="Data  Engineer", company="ACME")],
    }
    await ingest_source("fake")
    jobs = await jobs_by_ext(session)
    assert jobs["agg-9"].duplicate_of_id == jobs["1"].id
    assert jobs["1"].is_listed
    assert not jobs["agg-9"].is_listed
    assert (await last_run(session)).duplicates == 1

    # The original disappears: the duplicate is promoted and stays findable.
    fake.scopes = {
        "fake:a": [],
        "fake:agg": [posting("agg-9", title="Data  Engineer", company="ACME")],
    }
    await ingest_source("fake")
    jobs = await jobs_by_ext(session)
    assert jobs["agg-9"].duplicate_of_id is None
    assert jobs["agg-9"].is_listed


async def test_same_run_copies_never_hide_each_other(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.scopes = {"fake:a": [posting("1"), posting("2")]}  # identical title/company/location
    await ingest_source("fake")
    jobs = await jobs_by_ext(session)
    assert sum(j.is_listed for j in jobs.values()) == 1


async def test_invalid_postings_are_skipped(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    bad_url = posting("x")
    bad_url.apply_url = "javascript:alert(1)"
    fake.scopes = {"fake:a": [bad_url, posting("ok")]}
    await ingest_source("fake")
    assert set(await jobs_by_ext(session)) == {"ok"}


async def test_unconfigured_source_records_a_failed_run(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake.ready = "Set FAKE_API_KEY"
    await ingest_source("fake", trigger="manual")
    run = await last_run(session)
    assert (run.status, run.errors) == (RunStatus.FAILED, ["Set FAKE_API_KEY"])


async def test_concurrent_runs_are_skipped(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    session.add(
        IngestionRun(
            source_id=fake_source.id, trigger="schedule", status=RunStatus.RUNNING, errors=[]
        )
    )
    await session.commit()
    assert await ingest_source("fake") is None


async def test_disabled_sources_only_run_manually(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> None:
    fake_source.enabled = False
    await session.commit()
    fake.scopes = {"fake:a": [posting("1")]}
    assert await ingest_source("fake") is None
    assert await ingest_source("fake", trigger="manual") is not None


async def test_scheduling(session: AsyncSession, fake: FakePlugin, fake_source: JobSource) -> None:
    now = datetime.now(UTC)
    assert is_due(fake_source, now)
    fake_source.last_run_at = now - timedelta(minutes=30)
    fake_source.schedule_minutes = 60
    assert not is_due(fake_source, now)
    fake_source.last_run_at = now - timedelta(minutes=61)
    assert is_due(fake_source, now)
    await session.commit()

    fake.scopes = {"fake:a": [posting("1")]}
    assert await ingest_due_sources() == ["fake"]
    await drain_inline_jobs()
    assert set(await jobs_by_ext(session)) == {"1"}


async def test_ats_runs_update_company_health(session: AsyncSession) -> None:
    class BoardPlugin(FakePlugin):
        key = "greenhouse"
        uses_company_boards = True

        async def fetch(self, ctx: FetchContext) -> AsyncIterator[ScopeResult]:
            for board in ctx.boards:
                yield ScopeResult(
                    f"greenhouse:{board.board_token}",
                    [posting(f"{board.board_token}-1", company=board.name)],
                    company_id=board.company_id,
                )

    original = registry.PLUGINS["greenhouse"]
    registry.PLUGINS["greenhouse"] = BoardPlugin()
    try:
        await catalog.ensure_sources(session)
        session.add_all(
            [
                Company(name="Acme", slug="acme", ats=ATS.GREENHOUSE, board_token="acme"),
                Company(
                    name="Off", slug="off", ats=ATS.GREENHOUSE, board_token="off", enabled=False
                ),
            ]
        )
        await session.commit()
        await ingest_source("greenhouse")
    finally:
        registry.PLUGINS["greenhouse"] = original
    session.expire_all()
    acme = await session.scalar(select(Company).where(Company.slug == "acme"))
    assert acme is not None
    assert (acme.active_jobs, acme.last_error) == (1, None)
    assert acme.last_fetched_at is not None
    assert set(await jobs_by_ext(session)) == {"acme-1"}  # disabled boards are not read


async def test_seed_is_idempotent(session: AsyncSession) -> None:
    first = await catalog.seed(session)
    second = await catalog.seed(session)
    assert first.created >= 50
    assert (second.created, second.updated) == (0, 0)
    keys = {s.key for s in await session.scalars(select(JobSource))}
    assert {"greenhouse", "lever", "ashby", "adzuna"} <= keys
    adzuna = await session.scalar(select(JobSource).where(JobSource.key == "adzuna"))
    assert adzuna is not None
    assert adzuna.enabled is False  # needs an API key first


# --- search ---


@pytest.fixture
async def indexed(
    session: AsyncSession, fake: FakePlugin, fake_source: JobSource
) -> dict[str, Job]:
    fake.scopes = {
        "fake:a": [
            posting("py", title="Senior Python Engineer", body="<p>Python and Django</p>"),
            posting("fe", title="Frontend Engineer", company="Beta", location="Remote",
                    body="<p>React and TypeScript</p>"),
            posting("old", title="Python Developer", location="Pune, India", days_ago=40),
            posting("intern", title="Software Engineer Intern", company="Gamma",
                    location="Bangalore", body="<p>Java</p>"),
        ]
    }  # fmt: skip
    await ingest_source("fake")
    return await jobs_by_ext(session)


async def search(session: AsyncSession, **kwargs: Any) -> SearchHits:
    return await DatabaseSearchBackend().search(session, SearchQuery(**kwargs))


async def test_database_search_filters(session: AsyncSession, indexed: dict[str, Job]) -> None:
    ids = {j.id: name for name, j in indexed.items()}

    def names(hits: SearchHits) -> set[str]:
        return {ids[i] for i in hits.ids}

    assert names(await search(session, q="python")) == {"py", "old"}
    assert names(await search(session, work_modes=("remote",))) == {"fe"}
    assert names(await search(session, levels=("internship",))) == {"intern"}
    assert names(await search(session, skills=("React",))) == {"fe"}
    assert names(await search(session, location="bengaluru")) == {
        "py",
        "intern",
    }  # alias of Bangalore
    assert names(await search(session, posted_within_days=7)) == {"py", "fe", "intern"}
    assert names(await search(session, companies=("Beta",))) == {"fe"}
    facets = (await search(session)).facets
    assert facets["work_mode"]["remote"] == 1
    assert facets["experience_level"]["senior"] == 1


async def test_hidden_and_duplicate_jobs_are_never_found(
    session: AsyncSession, indexed: dict[str, Job]
) -> None:
    indexed["py"].is_hidden = True
    await session.commit()
    found = (await search(session, q="python")).ids
    assert indexed["py"].id not in found


async def test_search_falls_back_to_the_database(
    session: AsyncSession, indexed: dict[str, Job]
) -> None:
    class Broken(DatabaseSearchBackend):
        name = "meilisearch"

        async def search(self, session: AsyncSession, query: SearchQuery) -> SearchHits:
            raise ConnectionError("meilisearch is down")

    hits = await ResilientSearch(Broken(), DatabaseSearchBackend()).search(
        session, SearchQuery(q="react")
    )
    assert hits.backend == "database"
    assert hits.ids == [indexed["fe"].id]


# --- job seeker API ---


async def test_search_api_paginates_with_cursor(
    client: AsyncClient, login: LoginFn, indexed: dict[str, Job]
) -> None:
    headers = await login("seeker@example.com")
    first = (
        await client.get("/api/v1/jobs", params={"limit": 2, "sort": "newest"}, headers=headers)
    ).json()
    assert len(first["items"]) == 2
    assert first["total"] == 4
    assert first["search_backend"] == "database"
    second = (
        await client.get(
            "/api/v1/jobs", params={"limit": 2, "cursor": first["next_cursor"]}, headers=headers
        )
    ).json()
    assert second["next_cursor"] is None
    seen = [j["id"] for j in first["items"] + second["items"]]
    assert len(set(seen)) == 4

    card = first["items"][0]
    assert card["attribution"] == "Jobs by Fake"
    assert card["is_saved"] is False


async def test_search_api_validation(client: AsyncClient, login: LoginFn) -> None:
    headers = await login("seeker@example.com")
    bad_cursor = await client.get(
        "/api/v1/jobs", params={"cursor": "not-a-cursor"}, headers=headers
    )
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"]["code"] == "invalid_cursor"
    bad_mode = await client.get("/api/v1/jobs", params={"work_mode": "moon"}, headers=headers)
    assert bad_mode.status_code == 422
    assert (await client.get("/api/v1/jobs")).status_code == 401


async def test_job_detail_and_saved_jobs(
    client: AsyncClient, login: LoginFn, indexed: dict[str, Job], session: AsyncSession
) -> None:
    headers = await login("seeker@example.com")
    job_id = str(indexed["py"].id)
    detail = (await client.get(f"/api/v1/jobs/{job_id}", headers=headers)).json()
    assert detail["apply_url"] == "https://careers.example.com/py"
    assert "<p>Python and Django</p>" in detail["description_html"]

    assert (await client.put(f"/api/v1/jobs/{job_id}/save", headers=headers)).status_code == 204
    assert (
        await client.put(f"/api/v1/jobs/{job_id}/save", headers=headers)
    ).status_code == 204  # idempotent
    saved = (await client.get("/api/v1/jobs/saved", headers=headers)).json()
    assert [s["job"]["id"] for s in saved] == [job_id]
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=headers)).json()["is_saved"] is True
    listing = (
        await client.get("/api/v1/jobs", params={"q": "senior python"}, headers=headers)
    ).json()
    assert listing["items"][0]["is_saved"] is True

    await client.delete(f"/api/v1/jobs/{job_id}/save", headers=headers)
    assert (await client.get("/api/v1/jobs/saved", headers=headers)).json() == []

    indexed["py"].is_hidden = True
    await session.commit()
    assert (await client.get(f"/api/v1/jobs/{job_id}", headers=headers)).status_code == 404
    missing = await client.put(f"/api/v1/jobs/{uuid.uuid4()}/save", headers=headers)
    assert missing.status_code == 404


# --- admin API ---


@pytest.mark.parametrize(
    "path", ["/api/v1/admin/job-sources", "/api/v1/admin/companies", "/api/v1/admin/jobs"]
)
async def test_jobs_admin_needs_jobs_permission(
    client: AsyncClient, login: LoginFn, path: str
) -> None:
    from app.core.rbac import Role

    support = await login("helper@example.com", Role.SUPPORT)  # can read users, not manage jobs
    response = await client.get(path, headers=support)
    assert response.status_code == 403
    assert response.json()["error"]["details"] == {"missing": ["jobs:manage"]}


async def test_admin_manages_sources_and_runs(
    client: AsyncClient,
    login: LoginFn,
    fake: FakePlugin,
    fake_source: JobSource,
    session: AsyncSession,
) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    sources = (await client.get("/api/v1/admin/job-sources", headers=admin)).json()
    assert any(s["key"] == "fake" for s in sources)

    patched = await client.patch(
        "/api/v1/admin/job-sources/fake",
        json={"schedule_minutes": 120, "rate_limit_per_minute": 10, "enabled": False},
        headers=admin,
    )
    assert patched.status_code == 200
    assert (patched.json()["schedule_minutes"], patched.json()["enabled"]) == (120, False)
    too_fast = await client.patch(
        "/api/v1/admin/job-sources/fake", json={"schedule_minutes": 1}, headers=admin
    )
    assert too_fast.status_code == 422

    fake.scopes = {"fake:a": [posting("1")]}
    started = await client.post("/api/v1/admin/job-sources/fake/run", headers=admin)
    assert started.status_code == 202
    await drain_inline_jobs()
    runs = (await client.get("/api/v1/admin/job-sources/fake/runs", headers=admin)).json()
    assert runs[0]["trigger"] == "manual"
    assert runs[0]["created"] == 1

    fake.ready = "Missing key"
    blocked = await client.post("/api/v1/admin/job-sources/fake/run", headers=admin)
    assert blocked.status_code == 409
    actions = {a.action for a in await session.scalars(select(AuditLog))}
    assert {"job_source.updated", "job_source.run_requested"} <= actions


async def test_admin_manages_companies(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    body = {"name": "Acme", "ats": "lever", "board_token": "acme"}
    assert (
        await client.post("/api/v1/admin/companies", json=body, headers=admin)
    ).status_code == 201
    assert (
        await client.post("/api/v1/admin/companies", json=body, headers=admin)
    ).status_code == 409
    bad = await client.post(
        "/api/v1/admin/companies", json={**body, "board_token": "../etc"}, headers=admin
    )
    assert bad.status_code == 422

    csv = (
        b"# comment\nname,ats,board_token\n"
        b"Beta,greenhouse,beta\nBad,workday,x\nAcme Inc,lever,acme\n"
    )
    imported = await client.post(
        "/api/v1/admin/companies/import",
        files={"file": ("companies.csv", io.BytesIO(csv), "text/csv")},
        headers=admin,
    )
    result = imported.json()
    assert (result["created"], result["updated"], result["skipped"]) == (1, 1, 1)
    assert "row 3" in result["errors"][0]

    companies = (
        await client.get("/api/v1/admin/companies", params={"ats": "lever"}, headers=admin)
    ).json()
    assert [c["name"] for c in companies] == ["Acme Inc"]
    company_id = companies[0]["id"]
    disabled = await client.patch(
        f"/api/v1/admin/companies/{company_id}", json={"enabled": False}, headers=admin
    )
    assert disabled.json()["enabled"] is False
    assert (
        await client.delete(f"/api/v1/admin/companies/{company_id}", headers=admin)
    ).status_code == 204
    assert await session.get(Company, uuid.UUID(company_id)) is None


async def test_admin_hides_features_and_resolves_duplicates(
    client: AsyncClient,
    login: LoginFn,
    indexed: dict[str, Job],
    fake: FakePlugin,
    session: AsyncSession,
) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    job_id = str(indexed["fe"].id)
    hidden = await client.patch(
        f"/api/v1/admin/jobs/{job_id}", json={"hidden": True}, headers=admin
    )
    assert hidden.json()["is_hidden"] is True
    listed = (
        await client.get("/api/v1/admin/jobs", params={"status": "hidden"}, headers=admin)
    ).json()
    assert [j["id"] for j in listed["items"]] == [job_id]

    # Create a duplicate, then tell the system it isn't one.
    fake.scopes["fake:agg"] = [posting("dup", title="Senior Python Engineer")]
    await ingest_source("fake")
    dupes = (
        await client.get("/api/v1/admin/jobs", params={"status": "duplicate"}, headers=admin)
    ).json()
    assert dupes["total"] == 1
    assert dupes["items"][0]["duplicate_of_title"].startswith("Senior Python Engineer")
    dup_id = dupes["items"][0]["id"]
    resolved = await client.post(f"/api/v1/admin/jobs/{dup_id}/not-duplicate", headers=admin)
    assert resolved.json()["duplicate_of_id"] is None
    await ingest_source("fake")  # the override survives the next run
    session.expire_all()
    job = await session.get(Job, uuid.UUID(dup_id))
    assert job is not None
    assert job.duplicate_of_id is None

    again = await client.post(f"/api/v1/admin/jobs/{dup_id}/not-duplicate", headers=admin)
    assert again.status_code == 409


async def test_reindex_endpoint(
    client: AsyncClient, login: LoginFn, indexed: dict[str, Job]
) -> None:
    class Recorder(DatabaseSearchBackend):
        def __init__(self) -> None:
            self.docs: list[Job] = []

        async def upsert(self, jobs: list[Job]) -> None:
            self.docs.extend(jobs)

    recorder = Recorder()
    set_search(recorder)
    admin = await login(ROOT_ADMIN_EMAIL)
    response = await client.post("/api/v1/admin/search/reindex", headers=admin)
    assert response.json() == {"indexed": 4}
    assert len(recorder.docs) == 4
