"""JWT issuing and verification for GlideUp's own access and refresh tokens."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal

import jwt

from app.core.config import Settings
from app.core.errors import UnauthorizedError

TokenType = Literal["access", "refresh"]


@dataclass(frozen=True, slots=True)
class TokenClaims:
    subject: uuid.UUID
    token_type: TokenType
    jti: uuid.UUID
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    claims: TokenClaims


def _now() -> datetime:
    return datetime.now(UTC)


def create_token(
    settings: Settings, subject: uuid.UUID, token_type: TokenType, *, jti: uuid.UUID | None = None
) -> IssuedToken:
    issued_at = _now()
    ttl = (
        timedelta(minutes=settings.access_token_ttl_minutes)
        if token_type == "access"  # noqa: S105
        else timedelta(days=settings.refresh_token_ttl_days)
    )
    claims = TokenClaims(
        subject=subject,
        token_type=token_type,
        jti=jti or uuid.uuid4(),
        issued_at=issued_at,
        expires_at=issued_at + ttl,
    )
    payload = {
        "sub": str(claims.subject),
        "typ": token_type,
        "jti": str(claims.jti),
        "iat": int(issued_at.timestamp()),
        "exp": int(claims.expires_at.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }
    token = jwt.encode(
        payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return IssuedToken(token=token, claims=claims)


def decode_token(settings: Settings, token: str, expected_type: TokenType) -> TokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "typ", "jti", "iat", "exp"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Token has expired", code="token_expired") from exc
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid token", code="invalid_token") from exc

    if payload.get("typ") != expected_type:
        raise UnauthorizedError("Wrong token type", code="invalid_token")
    try:
        return TokenClaims(
            subject=uuid.UUID(payload["sub"]),
            token_type=expected_type,
            jti=uuid.UUID(payload["jti"]),
            issued_at=datetime.fromtimestamp(payload["iat"], UTC),
            expires_at=datetime.fromtimestamp(payload["exp"], UTC),
        )
    except (ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid token", code="invalid_token") from exc
