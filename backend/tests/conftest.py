"""Test fixtures.

Runs against SQLite by default (fast, zero setup). Set TEST_DATABASE_URL to a
Postgres URL to run the same suite against the real database, as CI does.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.rbac import Role
from app.db.base import Base
from app.db.models import User
from app.db.session import dispose_engine, get_engine, init_engine, session_factory
from app.main import create_app
from app.modules.auth.service import _grant, ensure_roles

ROOT_ADMIN_EMAIL = "root@glideup.dev"


@pytest.fixture(scope="session")
def settings(tmp_path_factory: pytest.TempPathFactory) -> Settings:
    db_file: Path = tmp_path_factory.mktemp("db") / "test.sqlite3"
    return Settings(
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
    )


@pytest.fixture(scope="session", autouse=True)
async def _database(settings: Settings) -> AsyncIterator[None]:
    init_engine(settings)
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await dispose_engine()


@pytest.fixture(autouse=True)
async def _clean_tables(_database: None) -> AsyncIterator[None]:
    yield
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
