"""Command-line staff management (bootstrap admins without the UI)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.core.rbac import Role
from app.db.models import AuditLog
from app.modules.admin import operator
from tests.conftest import LoginFn


async def test_grant_creates_account_that_signs_in_as_admin(
    session: AsyncSession, client: AsyncClient, login: LoginFn
) -> None:
    user, created = await operator.set_role(session, email=" Boss@Example.com ", role=Role.ADMIN)
    await session.commit()
    assert created
    assert (user.email, user.role_names) == ("boss@example.com", ["admin"])

    headers = await login("boss@example.com")  # first sign-in links to the existing account
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    assert me["roles"] == ["admin"]
    assert (await client.get("/api/v1/admin/overview", headers=headers)).status_code == 200

    actions = [
        (a.action, (a.after or {}).get("source")) for a in await session.scalars(select(AuditLog))
    ]
    assert ("user.created", "cli") in actions
    assert ("user.role_changed", "cli") in actions


async def test_grant_is_idempotent_and_revoke_needs_an_account(session: AsyncSession) -> None:
    await operator.set_role(session, email="a@example.com", role=Role.SUPPORT)
    _, created = await operator.set_role(session, email="a@example.com", role=Role.SUPPORT)
    assert not created
    with pytest.raises(NotFoundError):
        await operator.set_role(session, email="ghost@example.com", role=Role.USER, create=False)


async def test_last_super_admin_is_protected(session: AsyncSession) -> None:
    await operator.set_role(session, email="root@example.com", role=Role.SUPER_ADMIN)
    with pytest.raises(ConflictError):
        await operator.set_role(session, email="root@example.com", role=Role.USER)

    await operator.set_role(session, email="second@example.com", role=Role.SUPER_ADMIN)
    user, _ = await operator.set_role(session, email="root@example.com", role=Role.USER)
    assert user.role_names == ["user"]


async def test_list_staff_shows_only_privileged_accounts(
    session: AsyncSession, login: LoginFn
) -> None:
    await login("regular@example.com")
    await operator.set_role(session, email="editor@example.com", role=Role.CONTENT_EDITOR)
    await session.commit()
    rows = await operator.list_staff(session)
    assert [(r.email, r.roles, r.has_signed_in) for r in rows] == [
        ("editor@example.com", ["content_editor"], False)
    ]
