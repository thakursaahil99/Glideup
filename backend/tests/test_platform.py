"""Phase 9: rate limiting, LLM cache and budgets, feature flags, LLM settings, system health,
announcements and security headers."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core import redis as redis_client
from app.core.config import Settings
from app.db.models import AuditLog, FeatureFlag, FrameworkAttempt, LLMUsage, User
from app.llm import cache, runtime
from app.llm.factory import get_gateway
from app.llm.routing import routes_for
from app.llm.types import BudgetExceededError, CallContext, Message
from app.modules.platform.service import flag_on
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn


@pytest.fixture(autouse=True)
def fresh_runtime() -> Any:
    runtime.apply({})
    yield
    runtime.apply({})


# --- rate limiting ---


async def test_token_bucket_and_redis_fallback() -> None:
    limit = ratelimit.Limit(capacity=2, per_minute=60)
    assert (await ratelimit.take("t", "u1", limit))[0] is True
    assert (await ratelimit.take("t", "u1", limit))[0] is True
    allowed, wait_ms = await ratelimit.take("t", "u1", limit)
    assert allowed is False
    assert 0 < wait_ms <= 1000  # one token per second
    assert (await ratelimit.take("t", "u2", limit))[0] is True  # per subject
    # Tests point Redis at a dead port: the first call marks it down, later calls skip it.
    assert redis_client.get_redis() is None


async def test_expensive_endpoints_return_429(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    from app.modules.coding.service import seed_problems

    await seed_problems(session)
    await session.commit()
    headers = await login("busy@example.com")
    statuses = []
    for _ in range(ratelimit.LIMITS["code"].capacity + 1):
        response = await client.post(
            "/api/v1/problems/two-sum/run",
            json={"language": "python", "code": "x"},
            headers=headers,
        )
        statuses.append(response.status_code)
    assert statuses[:-1] == [200] * ratelimit.LIMITS["code"].capacity
    assert statuses[-1] == 429
    assert response.json()["error"]["details"]["retry_after"] >= 1
    other = await login("calm@example.com")
    assert (
        await client.post(
            "/api/v1/problems/two-sum/run", json={"language": "python", "code": "x"}, headers=other
        )
    ).status_code == 200  # limits are per user


# --- LLM cache, budget, routing overrides ---


class Answer(BaseModel):
    summary: str


class FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.data[key] = value


async def test_llm_responses_are_cached(
    monkeypatch: pytest.MonkeyPatch, session: AsyncSession
) -> None:
    fake = FakeRedis()
    monkeypatch.setattr(cache, "get_redis", lambda: fake)
    from app.llm.factory import MOCK_HANDLERS

    calls = {"n": 0}

    def handler(_: Any) -> str:
        calls["n"] += 1
        return '{"summary": "ok"}'

    monkeypatch.setitem(MOCK_HANDLERS, "skill_gap", handler)
    gateway = get_gateway()
    messages = [Message("user", "same prompt")]
    first, _ = await gateway.complete_json("skill_gap", messages, Answer)
    second, result = await gateway.complete_json("skill_gap", messages, Answer)
    assert first == second == Answer(summary="ok")
    assert calls["n"] == 1  # the second answer came from the cache
    assert result.provider == "mock"
    usage = list(await session.scalars(select(LLMUsage).where(LLMUsage.task == "skill_gap")))
    assert [u.cached for u in usage] == [False, True]

    runtime.apply({"llm.cache_enabled": False})
    await gateway.complete_json("skill_gap", messages, Answer)
    assert calls["n"] == 2
    # Conversational tasks are never cached.
    assert cache.eligible("interviewer", 0.1) is False


async def test_daily_token_budget(session: AsyncSession, login: LoginFn) -> None:
    await login("spender@example.com")
    user = await session.scalar(select(User).where(User.email == "spender@example.com"))
    assert user is not None
    session.add(
        LLMUsage(
            task="skill_gap",
            provider="mock",
            model="m",
            operation="complete",
            success=True,
            prompt_tokens=900,
            completion_tokens=200,
            latency_ms=1,
            user_id=user.id,
        )
    )
    await session.commit()
    gateway = get_gateway()
    gateway._token_cache.clear()
    runtime.apply({"llm.user_daily_token_budget": 1000})
    with pytest.raises(BudgetExceededError):
        await gateway.complete(
            "skill_gap", [Message("user", "hi")], ctx=CallContext(user_id=user.id)
        )
    gateway._token_cache.clear()
    runtime.apply({"llm.user_daily_token_budget": 5000})
    await gateway.complete("skill_gap", [Message("user", "hi")], ctx=CallContext(user_id=user.id))


def test_admin_route_overrides_win(settings: Settings) -> None:
    runtime.apply({"llm.routes": {"skill_gap": ["github:openai/gpt-4.1"]}})
    assert str(routes_for("skill_gap", settings)[0]) == "github:openai/gpt-4.1"
    runtime.apply({})
    assert str(routes_for("skill_gap", settings)[0]) == "mock:mock-1"


# --- feature flags ---


def test_flag_rules() -> None:
    flag = FeatureFlag(key="voice_mode", enabled=True, rollout_percent=100, allow_user_ids=[])
    assert flag_on(flag, "voice_mode", uuid.uuid4())
    flag.enabled = False
    tester = uuid.uuid4()
    flag.allow_user_ids = [str(tester)]
    assert not flag_on(flag, "voice_mode", uuid.uuid4())
    assert flag_on(flag, "voice_mode", tester)  # testers always get it
    flag.enabled, flag.allow_user_ids, flag.rollout_percent = True, [], 30
    users = [uuid.uuid4() for _ in range(400)]
    share = sum(flag_on(flag, "voice_mode", u) for u in users) / len(users)
    assert 0.2 < share < 0.4
    assert flag_on(flag, "voice_mode", users[0]) == flag_on(flag, "voice_mode", users[0])  # stable
    assert flag_on(None, "voice_mode", None) is True  # unconfigured: shipped default


async def test_flags_are_enforced(client: AsyncClient, login: LoginFn) -> None:
    from app.core.rbac import Role
    from app.modules.platform.service import invalidate_flags

    seeker = await login("seeker@example.com")
    assert (await client.get("/api/v1/me/flags", headers=seeker)).json()["framework_tests"] is True
    support = await login("helper@example.com", Role.SUPPORT)
    assert (await client.get("/api/v1/admin/flags", headers=support)).status_code == 403

    admin = await login(ROOT_ADMIN_EMAIL)
    flags = (await client.get("/api/v1/admin/flags", headers=admin)).json()
    assert {f["key"] for f in flags} >= {"voice_mode", "framework_tests", "ai_skill_gap"}
    off = await client.patch(
        "/api/v1/admin/flags/framework_tests", json={"enabled": False}, headers=admin
    )
    assert off.json()["enabled"] is False
    invalidate_flags()
    blocked = await client.post("/api/v1/frameworks/react/attempts", headers=seeker)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "feature_disabled"
    assert (await client.get("/api/v1/me/flags", headers=seeker)).json()["framework_tests"] is False


# --- LLM settings & usage ---


async def test_llm_settings_admin(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    from app.core.rbac import Role

    admin_role = await login("ops@example.com", Role.ADMIN)
    assert (
        await client.get("/api/v1/admin/llm/settings", headers=admin_role)
    ).status_code == 403  # super only
    root = await login(ROOT_ADMIN_EMAIL)
    current = (await client.get("/api/v1/admin/llm/settings", headers=root)).json()
    assert current["settings"]["llm.cache_enabled"] is True
    assert "skill_gap" in current["tasks"]

    bad = await client.put(
        "/api/v1/admin/llm/settings",
        json={"values": {"llm.routes": {"skill_gap": ["nope:x"]}}},
        headers=root,
    )
    assert bad.json()["error"]["code"] == "invalid_setting"
    two_embedders = await client.put(
        "/api/v1/admin/llm/settings",
        json={"values": {"llm.routes": {"embedding": ["mock:a", "mock:b"]}}},
        headers=root,
    )
    assert two_embedders.status_code == 400
    saved = await client.put(
        "/api/v1/admin/llm/settings",
        json={
            "values": {
                "llm.routes": {"skill_gap": ["mock:better"]},
                "llm.user_daily_token_budget": 50000,
            }
        },
        headers=root,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["effective_routes"]["skill_gap"][0] == "mock:better"
    assert runtime.get("llm.user_daily_token_budget") == 50000
    assert await session.scalar(
        select(AuditLog.action).where(AuditLog.action == "llm.settings_updated")
    )
    usage = (await client.get("/api/v1/admin/llm/usage", params={"days": 7}, headers=root)).json()
    assert isinstance(usage, list)


# --- system health & announcements ---


async def test_system_health_and_retry(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    from app.core.rbac import Role

    seeker = await login("seeker@example.com")
    attempt = (await client.post("/api/v1/frameworks/react/attempts", headers=seeker)).json()
    row = await session.get(FrameworkAttempt, uuid.UUID(attempt["id"]))
    assert row is not None
    from app.db.models import AttemptStatus

    row.status = AttemptStatus.FAILED
    row.error = "AI unavailable"
    await session.commit()

    support = await login("helper@example.com", Role.SUPPORT)
    health = (await client.get("/api/v1/admin/system/health", headers=support)).json()
    checks = {c["name"]: c for c in health["checks"]}
    assert checks["PostgreSQL"]["status"] == "ok"
    assert checks["Code sandbox"]["status"] == "off"  # fake runner in tests
    assert any(j["kind"] == "framework_grading" for j in health["failed_jobs"])
    path = f"/api/v1/admin/system/jobs/framework_grading/{attempt['id']}/retry"
    assert (await client.post(path, headers=support)).status_code == 403  # read-only role
    admin = await login(ROOT_ADMIN_EMAIL)
    assert (await client.post(path, headers=admin)).status_code == 202
    from app.workers.runtime import drain_inline_jobs

    await drain_inline_jobs()
    await session.refresh(row)
    assert row.status == AttemptStatus.GRADED


async def test_announcements(client: AsyncClient, login: LoginFn) -> None:
    admin = await login(ROOT_ADMIN_EMAIL)
    now = datetime.now(UTC)
    for body in (
        {"title": "Maintenance tonight", "level": "warning"},
        {"title": "Admins only", "audience": "admins"},
        {"title": "Old news", "ends_at": (now - timedelta(days=1)).isoformat()},
        {"title": "Not yet", "starts_at": (now + timedelta(days=1)).isoformat()},
    ):
        assert (
            await client.post("/api/v1/admin/announcements", json=body, headers=admin)
        ).status_code == 201
    seeker = await login("seeker@example.com")
    assert [
        a["title"] for a in (await client.get("/api/v1/announcements", headers=seeker)).json()
    ] == ["Maintenance tonight"]
    assert len((await client.get("/api/v1/announcements", headers=admin)).json()) == 2


async def test_security_headers_and_body_limit(client: AsyncClient, login: LoginFn) -> None:
    headers = await login("seeker@example.com")
    response = await client.get("/api/v1/me/flags", headers=headers)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    huge = await client.post(
        "/api/v1/reports",
        content=b"x" * (3 * 1024 * 1024),
        headers={**headers, "content-type": "application/json"},
    )
    assert huge.status_code == 413
