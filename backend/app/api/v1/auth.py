"""Token endpoints. Called server-to-server by the Next.js Auth.js callbacks."""

from fastapi import APIRouter, status

from app.api.deps import RequestMetaDep, SessionDep, SettingsDep
from app.api.v1.schemas import (
    DevSignInRequest,
    GoogleSignInRequest,
    RefreshRequest,
    TokenResponse,
)
from app.api.v1.users import to_me_response
from app.core.errors import ErrorResponse, NotFoundError
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


@router.post("/dev-login", response_model=TokenResponse, responses={404: {"model": ErrorResponse}})
async def sign_in_for_development(
    body: DevSignInRequest, session: SessionDep, settings: SettingsDep, meta: RequestMetaDep
) -> TokenResponse:
    """Password-less sign-in for local development only. Returns 404 unless explicitly enabled."""
    if not (settings.auth_dev_login_enabled and settings.is_local):
        raise NotFoundError("Not found")
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
