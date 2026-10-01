"""Test fixtures.

Runs against SQLite by default (fast, zero setup). Set TEST_DATABASE_URL to a
Postgres URL to run the same suite against the real database, as CI does.
"""

import io
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import storage
from app.core.config import Settings, get_settings, override_settings
from app.core.rbac import Role
from app.db.base import Base
from app.db.models import User
from app.db.session import dispose_engine, get_engine, init_engine, session_factory
from app.llm.factory import set_gateway
from app.main import create_app
from app.modules.auth.service import _grant, ensure_roles
from app.modules.jobs.search import set_search
from app.workers.runtime import drain_inline_jobs

ROOT_ADMIN_EMAIL = "root@glideup.dev"


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    db_file: Path = tmp_path_factory.mktemp("db") / "test.sqlite3"
    test_settings = Settings(
        _env_file=None,
        environment="test",
        database_url=os.getenv("TEST_DATABASE_URL", f"sqlite+aiosqlite:///{db_file.as_posix()}"),
        redis_url=os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:1/0"),
        jwt_secret="test-secret-that-is-long-enough-for-hs256-signing",
        auth_dev_login_enabled=True,
        admin_emails=[ROOT_ADMIN_EMAIL],
        google_client_id="test-client-id.apps.googleusercontent.com",
        metrics_enabled=False,
        log_json=False,
        log_level="WARNING",
        # Phase 2: no Redis, no MinIO, no real model in tests.
        task_execution="inline",
        storage_backend="local",
        local_storage_path=str(tmp_path_factory.mktemp("storage")),
        llm_routes={"resume_parse": ["mock:mock-1"], "embedding": ["mock:mock-1"]},
        llm_allow_mock_fallback=True,
        search_backend="database",
        inline_scheduler_minutes=0,
    )
    override_settings(test_settings)
    return test_settings


@pytest.fixture(scope="session", autouse=True)
async def _database(settings: Settings) -> AsyncIterator[None]:
    init_engine(settings)
    async with get_engine().begin() as conn:
        if conn.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_tables(_database: None) -> AsyncIterator[None]:
    set_gateway(None)  # fresh providers and circuit breakers per test
    set_search(None)
    storage._build.cache_clear()
    yield
    await drain_inline_jobs()
    async with get_engine().begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
async def session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as s:
        yield s


@pytest.fixture
async def client(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.dependency_overrides[get_settings] = lambda: settings
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


LoginFn = Callable[..., Awaitable[dict[str, str]]]


@pytest.fixture
def login(client: AsyncClient) -> LoginFn:
    """Sign in via the dev endpoint, optionally granting a role, and return auth headers."""

    async def _login(email: str, role: Role | None = None) -> dict[str, str]:
        if role is not None:
            await client.post("/api/v1/auth/dev-login", json={"email": email})
            async with session_factory()() as s:
                await ensure_roles(s)
                user = await s.scalar(select(User).where(User.email == email))
                assert user is not None
                await _grant(s, user, role)
                await s.commit()
        response = await client.post("/api/v1/auth/dev-login", json={"email": email})
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _login


def make_pdf(lines: list[str], pages: int = 1) -> bytes:
    """Build a real text PDF (what users upload) for tests."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for page in range(pages):
        y = 800
        for line in lines if page == 0 else [f"Page {page + 1}"]:
            pdf.drawString(50, y, line)
            y -= 16
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


SAMPLE_RESUME_LINES = [
    "Asha Verma",
    "Senior Backend Engineer",
    "asha.verma@example.com | github.com/ashaverma | Bengaluru, India",
    "Summary: Backend engineer with 7 years of experience building APIs and data platforms.",
    "Skills: Python, FastAPI, Django, PostgreSQL, Redis, Docker, Kubernetes, AWS, React, Git",
    "Experience",
    "Senior Backend Engineer - Example Corp (2021 - present)",
    "Designed REST APIs serving 2M requests per day with FastAPI and PostgreSQL.",
    "Backend Engineer - Sample Systems (2018 - 2021)",
    "Built Django services, Celery pipelines and CI/CD with GitHub Actions.",
    "Education: B.Tech Computer Science, Example Institute of Technology, 2018",
]


@pytest.fixture
def resume_pdf() -> bytes:
    return make_pdf(SAMPLE_RESUME_LINES)


UseSettings = Callable[..., Settings]


@pytest.fixture
def use_settings(settings: Settings) -> Iterator[UseSettings]:
    """Apply setting changes for one test (services read global settings); auto-restored."""

    def _apply(**changes: object) -> Settings:
        changed = settings.model_copy(update=changes)
        override_settings(changed)
        set_gateway(None)
        storage._build.cache_clear()
        return changed

    yield _apply
    override_settings(settings)
    set_gateway(None)
