"""Token endpoints. Called server-to-server by the Next.js Auth.js callbacks."""

import hmac

from fastapi import APIRouter, status

from app.api.deps import RequestMetaDep, SessionDep, SettingsDep
from app.api.v1.schemas import (
    DevSignInRequest,
    GoogleSignInRequest,
    PasswordSignInRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
)
from app.api.v1.users import to_me_response
from app.core.errors import ErrorResponse, NotFoundError, UnauthorizedError
from app.core.ratelimit import enforce
from app.db.models import User
from app.modules.auth import service
from app.modules.auth.google import verify_google_id_token
from app.modules.auth.service import TokenPair

router = APIRouter(
    prefix="/auth",
    tags=["auth"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)


def _token_response(user: User, pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=pair.access_token,
        refresh_token=pair.refresh_token,
        access_expires_at=pair.access_expires_at,
        refresh_expires_at=pair.refresh_expires_at,
        user=to_me_response(user),
    )


@router.post("/google", response_model=TokenResponse)
async def sign_in_with_google(
    body: GoogleSignInRequest, session: SessionDep, settings: SettingsDep, meta: RequestMetaDep
) -> TokenResponse:
    """Exchange a Google ID token (from Auth.js) for GlideUp access + refresh tokens."""
    identity = await verify_google_id_token(settings, body.id_token)
    user, pair = await service.sign_in(
        session,
        settings,
        email=identity.email,
        name=identity.name,
        avatar_url=identity.picture,
        google_sub=identity.sub,
        meta=meta,
    )
    return _token_response(user, pair)


@router.post("/register", response_model=TokenResponse, responses={409: {"model": ErrorResponse}})
async def register(
    body: RegisterRequest, session: SessionDep, settings: SettingsDep, meta: RequestMetaDep
) -> TokenResponse:
    """Create an email + password account. Returns 404 when registration is switched off."""
    if not settings.auth_registration_enabled:
        raise NotFoundError("Not found")
    await enforce("auth", str(body.email).lower())
    user, pair = await service.register(
        session,
        settings,
        email=str(body.email),
        name=body.name,
        password=body.password,
        meta=meta,
    )
    return _token_response(user, pair)


@router.post("/login", response_model=TokenResponse)
async def sign_in_with_password(
    body: PasswordSignInRequest, session: SessionDep, settings: SettingsDep, meta: RequestMetaDep
) -> TokenResponse:
    """Sign in to an email + password account."""
    await enforce("auth", str(body.email).lower())
    user, pair = await service.password_sign_in(
        session, settings, email=str(body.email), password=body.password, meta=meta
    )
    return _token_response(user, pair)


@router.post("/dev-login", response_model=TokenResponse, responses={404: {"model": ErrorResponse}})
async def sign_in_for_development(
    body: DevSignInRequest, session: SessionDep, settings: SettingsDep, meta: RequestMetaDep
) -> TokenResponse:
    """Email sign-in. Password-less for local development; elsewhere it needs the shared
    AUTH_DEV_LOGIN_PASSWORD. Returns 404 unless explicitly enabled."""
    password = settings.auth_dev_login_password
    if not (settings.auth_dev_login_enabled and (settings.is_local or password)):
        raise NotFoundError("Not found")
    if password and not hmac.compare_digest(
        (body.password or "").encode(), password.get_secret_value().encode()
    ):
        raise UnauthorizedError("Wrong email or password")
    user, pair = await service.sign_in(
        session,
        settings,
        email=str(body.email),
        name=body.name,
        avatar_url=None,
        google_sub=None,
        meta=meta,
    )
    return _token_response(user, pair)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    body: RefreshRequest, session: SessionDep, settings: SettingsDep, meta: RequestMetaDep
) -> TokenResponse:
    """Rotate a refresh token: the old one is revoked, a new pair is returned."""
    user, pair = await service.rotate_refresh_token(
        session, settings, body.refresh_token, user_agent=meta.user_agent
    )
    await session.refresh(user, ["roles"])
    return _token_response(user, pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(body: RefreshRequest, session: SessionDep, settings: SettingsDep) -> None:
    await service.revoke_refresh_token(session, settings, body.refresh_token)
