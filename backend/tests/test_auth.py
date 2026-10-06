from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1 import auth as auth_router
from app.core.config import Settings, get_settings
from app.core.errors import UnauthorizedError
from app.core.rbac import Role
from app.db.models import AuditLog, RefreshToken, User, UserStatus
from app.main import create_app
from app.modules.auth.google import GoogleIdentity
from tests.conftest import ROOT_ADMIN_EMAIL, LoginFn


async def dev_login(client: AsyncClient, email: str = "pilot@example.com") -> dict[str, object]:
    response = await client.post("/api/v1/auth/dev-login", json={"email": email, "name": "Pilot"})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


async def test_dev_login_creates_user_with_default_role(client: AsyncClient) -> None:
    body = await dev_login(client)
    user = body["user"]
    assert isinstance(user, dict)
    assert user["email"] == "pilot@example.com"
    assert user["roles"] == ["user"]
    assert user["permissions"] == []
    assert body["token_type"] == "bearer"


async def test_dev_login_is_idempotent(client: AsyncClient, session: AsyncSession) -> None:
    await dev_login(client)
    await dev_login(client, "PILOT@example.com")
    users = (await session.scalars(select(User))).all()
    assert len(users) == 1


async def test_dev_login_disabled_returns_404(settings: Settings) -> None:
    disabled = settings.model_copy(update={"auth_dev_login_enabled": False})
    app = create_app(disabled)
    app.dependency_overrides[get_settings] = lambda: disabled
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/api/v1/auth/dev-login", json={"email": "x@example.com"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_allowlisted_email_becomes_super_admin_and_is_audited(
    client: AsyncClient, session: AsyncSession
) -> None:
    body = await dev_login(client, ROOT_ADMIN_EMAIL)
    user = body["user"]
    assert isinstance(user, dict)
    assert "super_admin" in user["roles"]
    assert "admin:access" in user["permissions"]

    logs = (await session.scalars(select(AuditLog))).all()
    assert [log.action for log in logs] == ["user.role_granted"]
    assert logs[0].after == {"role": "super_admin", "source": "ADMIN_EMAILS allowlist"}

    # Signing in again must not grant or audit twice.
    await dev_login(client, ROOT_ADMIN_EMAIL)
    assert len((await session.scalars(select(AuditLog))).all()) == 1


async def test_me_requires_auth(client: AsyncClient) -> None:
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert response.headers["www-authenticate"] == "Bearer"


async def test_me_returns_current_user(client: AsyncClient) -> None:
    body = await dev_login(client)
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert response.status_code == 200
    assert response.json()["email"] == "pilot@example.com"


async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient) -> None:
    body = await dev_login(client)
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {body['refresh_token']}"}
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


async def test_expired_access_token_is_rejected(client: AsyncClient, settings: Settings) -> None:
    body = await dev_login(client)
    claims = jwt.decode(str(body["access_token"]), options={"verify_signature": False})
    claims["exp"] = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    expired = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm="HS256")
    response = await client.get("/api/v1/users/me", headers={"Authorization": f"Bearer {expired}"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_expired"


async def test_refresh_rotates_tokens(client: AsyncClient, session: AsyncSession) -> None:
    body = await dev_login(client)
    response = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert response.status_code == 200, response.text
    rotated = response.json()
    assert rotated["refresh_token"] != body["refresh_token"]

    tokens = (await session.scalars(select(RefreshToken))).all()
    assert len(tokens) == 2
    old = next(t for t in tokens if t.revoked_at is not None)
    assert old.replaced_by_id is not None


async def _age_revoked_tokens(session: AsyncSession, *, seconds: int) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.revoked_at.is_not(None))
        .values(revoked_at=datetime.now(UTC) - timedelta(seconds=seconds))
    )
    await session.commit()


async def test_parallel_refresh_within_grace_window_succeeds(
    client: AsyncClient, session: AsyncSession
) -> None:
    body = await dev_login(client)
    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    second = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert first.status_code == 200
    assert second.status_code == 200, second.text
    # Both new tokens keep working; nobody was logged out.
    for response in (first, second):
        again = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": response.json()["refresh_token"]}
        )
        assert again.status_code == 200


async def test_logged_out_token_gets_no_grace(client: AsyncClient) -> None:
    body = await dev_login(client)
    await client.post("/api/v1/auth/logout", json={"refresh_token": body["refresh_token"]})
    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "token_reused"


async def test_refresh_token_reuse_revokes_every_session(
    client: AsyncClient, session: AsyncSession
) -> None:
    body = await dev_login(client)
    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert first.status_code == 200
    await _age_revoked_tokens(session, seconds=120)  # well past the grace window

    replay = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]}
    )
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "token_reused"

    # The legitimately rotated token is now dead too.
    after = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": first.json()["refresh_token"]}
    )
    assert after.status_code == 401
    assert all(
        t.revoked_at is not None for t in (await session.scalars(select(RefreshToken))).all()
    )


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    body = await dev_login(client)
    response = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": body["refresh_token"]}
    )
    assert response.status_code == 204
    again = await client.post("/api/v1/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert again.status_code == 401


async def test_logout_with_garbage_token_is_a_noop(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/logout", json={"refresh_token": "x" * 40})
    assert response.status_code == 204


async def test_suspended_user_is_blocked(client: AsyncClient, session: AsyncSession) -> None:
    body = await dev_login(client)
    user = await session.scalar(select(User))
    assert user is not None
    user.status = UserStatus.SUSPENDED
    await session.commit()

    me = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.status_code == 403
    assert me.json()["error"]["code"] == "account_suspended"
    relogin = await client.post("/api/v1/auth/dev-login", json={"email": "pilot@example.com"})
    assert relogin.status_code == 403


async def test_google_sign_in(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_verify(_: Settings, token: str) -> GoogleIdentity:
        assert token == "g" * 40
        return GoogleIdentity(sub="google-123", email="flyer@gmail.com", name="Flyer", picture=None)

    monkeypatch.setattr(auth_router, "verify_google_id_token", fake_verify)
    response = await client.post("/api/v1/auth/google", json={"id_token": "g" * 40})
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == "flyer@gmail.com"


async def test_google_sign_in_rejects_bad_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_verify(_: Settings, __: str) -> GoogleIdentity:
        raise UnauthorizedError("Invalid Google token", code="invalid_google_token")

    monkeypatch.setattr(auth_router, "verify_google_id_token", fake_verify)
    response = await client.post("/api/v1/auth/google", json={"id_token": "g" * 40})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_google_token"


async def test_validation_errors_use_the_error_envelope(client: AsyncClient) -> None:
    response = await client.post("/api/v1/auth/dev-login", json={"email": "not-an-email"})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert error["details"][0]["loc"] == ["body", "email"]
    assert error["request_id"] == response.headers["x-request-id"]


async def test_login_fixture_grants_role(client: AsyncClient, login: LoginFn) -> None:
    headers = await login("editor@example.com", Role.CONTENT_EDITOR)
    me = (await client.get("/api/v1/users/me", headers=headers)).json()
    assert set(me["roles"]) == {"user", "content_editor"}


async def test_dev_login_with_password_outside_local(settings: Settings) -> None:
    hosted = settings.model_copy(
        update={
            "environment": "production",
            "auth_dev_login_password": SecretStr("a-long-shared-password"),
        }
    )
    app = create_app(hosted)
    app.dependency_overrides[get_settings] = lambda: hosted
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        url = "/api/v1/auth/dev-login"
        missing = await c.post(url, json={"email": "x@example.com"})
        wrong = await c.post(url, json={"email": "x@example.com", "password": "nope"})
        right = await c.post(
            url, json={"email": "x@example.com", "password": "a-long-shared-password"}
        )
    assert missing.status_code == wrong.status_code == 401
    assert right.status_code == 200


async def test_dev_login_outside_local_without_password_returns_404(settings: Settings) -> None:
    hosted = settings.model_copy(update={"environment": "production"})
    app = create_app(hosted)
    app.dependency_overrides[get_settings] = lambda: hosted
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post("/api/v1/auth/dev-login", json={"email": "x@example.com"})
    assert response.status_code == 404


def test_production_dev_login_needs_strong_password() -> None:
    base = {"_env_file": None, "environment": "production", "jwt_secret": "x" * 40}
    with pytest.raises(ValueError, match="AUTH_DEV_LOGIN_PASSWORD"):
        Settings(**base, auth_dev_login_enabled=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="AUTH_DEV_LOGIN_PASSWORD"):
        Settings(**base, auth_dev_login_enabled=True, auth_dev_login_password="short")  # type: ignore[arg-type]
    ok = Settings(**base, auth_dev_login_enabled=True, auth_dev_login_password="x" * 12)  # type: ignore[arg-type]
    assert ok.auth_dev_login_enabled
