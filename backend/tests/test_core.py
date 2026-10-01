"""Unit tests for config, RBAC, tokens, Google verification and health probes."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import AsyncClient
from pydantic import ValidationError

from app.api.v1 import health
from app.core.config import Settings
from app.core.errors import UnauthorizedError
from app.core.rbac import Permission, Role, highest_rank, permissions_for
from app.core.security import create_token, decode_token
from app.modules.auth import google

# --- config ---


def test_csv_env_values_are_split(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", "A@x.com, b@y.com")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000,https://glideup.app")
    settings = Settings(_env_file=None)
    assert settings.admin_emails == ["a@x.com", "b@y.com"]
    assert settings.cors_origins == ["http://localhost:3000", "https://glideup.app"]


def test_production_refuses_dev_login() -> None:
    with pytest.raises(ValidationError, match="AUTH_DEV_LOGIN_ENABLED"):
        Settings(
            _env_file=None,
            environment="production",
            auth_dev_login_enabled=True,
            jwt_secret="x" * 40,
        )


def test_production_refuses_weak_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        Settings(_env_file=None, environment="production", jwt_secret="short")


# --- RBAC ---


def test_super_admin_has_every_permission() -> None:
    assert permissions_for(["super_admin"]) == frozenset(Permission)


def test_permissions_union_across_roles_and_ignore_unknown() -> None:
    granted = permissions_for(["support", "content_editor", "pilot"])
    assert Permission.USERS_READ in granted
    assert Permission.QUESTIONS_MANAGE in granted
    assert Permission.USERS_WRITE not in granted


def test_user_role_has_no_admin_permissions() -> None:
    assert permissions_for([Role.USER]) == frozenset()


def test_highest_rank() -> None:
    assert highest_rank(["user", "admin"]) > highest_rank(["support"])
    assert highest_rank([]) == 0


# --- our JWTs ---


def test_token_round_trip(settings: Settings) -> None:
    subject = uuid.uuid4()
    issued = create_token(settings, subject, "access")
    claims = decode_token(settings, issued.token, "access")
    assert claims.subject == subject
    assert claims.jti == issued.claims.jti


def test_token_with_wrong_audience_is_rejected(settings: Settings) -> None:
    issued = create_token(settings, uuid.uuid4(), "access")
    other = settings.model_copy(update={"jwt_audience": "someone-else"})
    with pytest.raises(UnauthorizedError):
        decode_token(other, issued.token, "access")


def test_tampered_token_is_rejected(settings: Settings) -> None:
    issued = create_token(settings, uuid.uuid4(), "access")
    with pytest.raises(UnauthorizedError):
        decode_token(settings, issued.token[:-2] + "xx", "access")


# --- Google ID token verification ---


@pytest.fixture
def google_key(monkeypatch: pytest.MonkeyPatch) -> rsa.RSAPrivateKey:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class FakeJWKClient:
        def get_signing_key_from_jwt(self, _: str) -> Any:
            return type("Key", (), {"key": key.public_key()})()

    monkeypatch.setattr(google, "_jwks_client", lambda _url: FakeJWKClient())
    return key


def _google_token(key: rsa.RSAPrivateKey, settings: Settings, **overrides: Any) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": "https://accounts.google.com",
        "aud": settings.google_client_id,
        "sub": "1234567890",
        "email": "Flyer@Gmail.com",
        "email_verified": True,
        "name": "Flyer",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        **overrides,
    }
    return jwt.encode(claims, key, algorithm="RS256")


async def test_google_token_is_verified(google_key: rsa.RSAPrivateKey, settings: Settings) -> None:
    identity = await google.verify_google_id_token(settings, _google_token(google_key, settings))
    assert identity.sub == "1234567890"
    assert identity.email == "flyer@gmail.com"


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"aud": "another-app"}, "invalid_google_token"),
        ({"iss": "https://evil.example.com"}, "invalid_google_token"),
        ({"exp": 1}, "invalid_google_token"),
        ({"email_verified": False}, "email_not_verified"),
    ],
)
async def test_bad_google_tokens_are_rejected(
    google_key: rsa.RSAPrivateKey, settings: Settings, overrides: dict[str, Any], code: str
) -> None:
    with pytest.raises(UnauthorizedError) as excinfo:
        await google.verify_google_id_token(
            settings, _google_token(google_key, settings, **overrides)
        )
    assert excinfo.value.code == code


async def test_google_not_configured(settings: Settings) -> None:
    unconfigured = settings.model_copy(update={"google_client_id": None})
    with pytest.raises(UnauthorizedError) as excinfo:
        await google.verify_google_id_token(unconfigured, "token")
    assert excinfo.value.code == "google_not_configured"


# --- health probes ---


async def test_liveness(client: AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) == 32


async def test_request_id_is_propagated(client: AsyncClient) -> None:
    response = await client.get("/healthz", headers={"x-request-id": "trace-abc-12345"})
    assert response.headers["x-request-id"] == "trace-abc-12345"


async def test_readiness_reports_unreachable_redis(client: AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"].startswith("error")


async def test_readiness_ok_when_dependencies_are_up(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fine(_: str) -> None:
        return None

    monkeypatch.setattr(health, "_check_redis", fine)
    response = await client.get("/readyz")
    assert response.status_code == 200
    assert response.json()["checks"] == {"database": "ok", "redis": "ok"}


# --- Celery ---


def test_ping_task_runs_eagerly() -> None:
    from app.workers.tasks import ping

    assert ping.apply().get() == "pong"
