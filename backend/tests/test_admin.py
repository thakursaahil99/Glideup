import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role
from app.db.models import AuditLog, RefreshToken, User
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn


async def user_id(session: AsyncSession, email: str) -> str:
    user = await session.scalar(select(User).where(User.email == email))
    assert user is not None
    return str(user.id)


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/overview",
        "/api/v1/admin/users",
        "/api/v1/admin/audit-logs",
        "/api/v1/admin/roles",
    ],
)
async def test_regular_users_cannot_reach_admin(
    client: AsyncClient, login: LoginFn, path: str
) -> None:
    headers = await login("pilot@example.com")
    response = await client.get(path, headers=headers)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_overview_counts(client: AsyncClient, login: LoginFn) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    await login("a@example.com")
    await login("b@example.com")

    response = await client.get("/api/v1/admin/overview", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total_users"] == 3
    assert data["active_users_30d"] == 3
    assert data["new_users_in_range"] == 3
    assert data["admin_users"] == 1
    assert len(data["signups_by_day"]) == 30
    assert sum(d["count"] for d in data["signups_by_day"]) == 3


async def test_overview_rejects_inverted_range(client: AsyncClient, login: LoginFn) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    response = await client.get(
        "/api/v1/admin/overview",
        params={"start": "2026-02-01T00:00:00", "end": "2026-01-01T00:00:00"},
        headers=headers,
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_range"


async def test_list_users_search_and_filter(client: AsyncClient, login: LoginFn) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    await login("alice@example.com")
    await login("bob@example.com", Role.SUPPORT)

    found = (
        await client.get("/api/v1/admin/users", params={"search": "ALI"}, headers=headers)
    ).json()
    assert [u["email"] for u in found["items"]] == ["alice@example.com"]
    assert found["total"] == 1

    support = (
        await client.get("/api/v1/admin/users", params={"role": "support"}, headers=headers)
    ).json()
    assert [u["email"] for u in support["items"]] == ["bob@example.com"]

    paged = (
        await client.get("/api/v1/admin/users", params={"page_size": 2}, headers=headers)
    ).json()
    assert len(paged["items"]) == 2
    assert paged["total"] == 3


async def test_super_admin_changes_role_and_it_is_audited(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    await login("alice@example.com")
    alice = await user_id(session, "alice@example.com")

    response = await client.put(
        f"/api/v1/admin/users/{alice}/role", json={"role": "admin"}, headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["roles"] == ["admin"]

    log = await session.scalar(select(AuditLog).where(AuditLog.action == "user.role_changed"))
    assert log is not None
    assert log.actor_email == ROOT_ADMIN_EMAIL
    assert log.target_id == alice
    assert log.before == {"roles": ["user"]}
    assert log.after == {"roles": ["admin"]}


async def test_admin_cannot_grant_admin_roles(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login("boss@example.com", Role.ADMIN)
    await login("alice@example.com")
    alice = await user_id(session, "alice@example.com")

    denied = await client.put(
        f"/api/v1/admin/users/{alice}/role", json={"role": "admin"}, headers=headers
    )
    assert denied.status_code == 403

    allowed = await client.put(
        f"/api/v1/admin/users/{alice}/role", json={"role": "content_editor"}, headers=headers
    )
    assert allowed.status_code == 200
    assert allowed.json()["roles"] == ["content_editor"]


async def test_admin_cannot_modify_super_admin(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    await login(ROOT_ADMIN_EMAIL)
    headers = await login("boss@example.com", Role.ADMIN)
    root = await user_id(session, ROOT_ADMIN_EMAIL)
    response = await client.put(
        f"/api/v1/admin/users/{root}/status", json={"status": "suspended"}, headers=headers
    )
    assert response.status_code == 403


async def test_cannot_change_own_role(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    me = await user_id(session, ROOT_ADMIN_EMAIL)
    response = await client.put(
        f"/api/v1/admin/users/{me}/role", json={"role": "user"}, headers=headers
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "self_modification"


async def test_demoted_super_admin_loses_access_immediately(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    root_headers = await login(ROOT_ADMIN_EMAIL)
    other_headers = await login("second@example.com", Role.SUPER_ADMIN)
    root = await user_id(session, ROOT_ADMIN_EMAIL)
    second = await user_id(session, "second@example.com")

    # One super admin demotes the other...
    ok = await client.put(
        f"/api/v1/admin/users/{second}/role", json={"role": "user"}, headers=root_headers
    )
    assert ok.status_code == 200
    # ...and the demoted one has immediately lost access (roles are read per request).
    lost = await client.put(
        f"/api/v1/admin/users/{root}/role", json={"role": "user"}, headers=other_headers
    )
    assert lost.status_code == 403


async def test_suspend_revokes_sessions_and_unsuspend_restores(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    alice_headers = await login("alice@example.com")
    alice = await user_id(session, "alice@example.com")

    response = await client.put(
        f"/api/v1/admin/users/{alice}/status",
        json={"status": "suspended", "reason": "spam"},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"
    assert (await client.get("/api/v1/users/me", headers=alice_headers)).status_code == 403

    tokens = (
        await session.scalars(select(RefreshToken).where(RefreshToken.user_id == uuid.UUID(alice)))
    ).all()
    assert tokens
    assert all(t.revoked_at is not None for t in tokens)

    restored = await client.put(
        f"/api/v1/admin/users/{alice}/status", json={"status": "active"}, headers=headers
    )
    assert restored.json()["status"] == "active"

    actions = {log.action for log in (await session.scalars(select(AuditLog))).all()}
    assert {"user.suspended", "user.unsuspended"} <= actions


async def test_support_is_read_only(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login("helper@example.com", Role.SUPPORT)
    await login("alice@example.com")
    alice = await user_id(session, "alice@example.com")

    assert (await client.get("/api/v1/admin/users", headers=headers)).status_code == 200
    assert (await client.get("/api/v1/admin/audit-logs", headers=headers)).status_code == 200
    write = await client.put(
        f"/api/v1/admin/users/{alice}/status", json={"status": "suspended"}, headers=headers
    )
    assert write.status_code == 403
    assert write.json()["error"]["details"] == {"missing": ["users:write"]}


async def test_unknown_user_returns_404(client: AsyncClient, login: LoginFn) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    response = await client.put(
        "/api/v1/admin/users/00000000-0000-0000-0000-000000000000/role",
        json={"role": "user"},
        headers=headers,
    )
    assert response.status_code == 404


async def test_audit_log_filters(
    client: AsyncClient, login: LoginFn, session: AsyncSession
) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    await login("alice@example.com")
    alice = await user_id(session, "alice@example.com")
    await client.put(f"/api/v1/admin/users/{alice}/role", json={"role": "support"}, headers=headers)

    everything = (await client.get("/api/v1/admin/audit-logs", headers=headers)).json()
    assert everything["total"] == 2  # allowlist grant + role change

    changed = (
        await client.get(
            "/api/v1/admin/audit-logs", params={"action": "user.role_changed"}, headers=headers
        )
    ).json()
    assert [i["target_id"] for i in changed["items"]] == [alice]

    by_target = (
        await client.get("/api/v1/admin/audit-logs", params={"target_id": alice}, headers=headers)
    ).json()
    assert by_target["total"] == 1


async def test_roles_endpoint_lists_permission_matrix(client: AsyncClient, login: LoginFn) -> None:
    headers = await login(ROOT_ADMIN_EMAIL)
    roles = (await client.get("/api/v1/admin/roles", headers=headers)).json()
    by_name = {r["name"]: r for r in roles}
    assert set(by_name) == {r.value for r in Role}
    assert by_name["user"]["permissions"] == []
    assert "llm:manage" in by_name["super_admin"]["permissions"]
    assert "llm:manage" not in by_name["admin"]["permissions"]
