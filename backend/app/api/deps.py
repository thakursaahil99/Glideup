"""Shared FastAPI dependencies: settings, DB session, current user, permission checks."""

from collections.abc import Awaitable, Callable
from typing import Annotated

import structlog
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.core.rbac import Permission, permissions_for
from app.core.security import decode_token
from app.db.models import User
from app.db.session import get_session
from app.modules.audit.service import RequestMeta

SettingsDep = Annotated[Settings, Depends(get_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False, description="GlideUp access token")


async def get_current_user(
    session: SessionDep,
    settings: SettingsDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> User:
    if credentials is None:
        raise UnauthorizedError("Not authenticated")
    claims = decode_token(settings, credentials.credentials, "access")
    # Load the user on every request so suspensions and role changes apply immediately,
    # not when the access token happens to expire.
    user = await session.get(User, claims.subject)
    if user is None:
        raise UnauthorizedError("User no longer exists", code="invalid_token")
    if not user.is_active:
        raise ForbiddenError("This account is suspended", code="account_suspended")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*required: Permission) -> Callable[[User], Awaitable[User]]:
    """Dependency factory: the caller must hold *all* of the given permissions."""

    async def checker(user: CurrentUser) -> User:
        granted = permissions_for(user.role_names)
        missing = [p.value for p in required if p not in granted]
        if missing:
            raise ForbiddenError(
                "You do not have permission to do this", details={"missing": missing}
            )
        return user

    return checker


def get_request_meta(request: Request) -> RequestMeta:
    forwarded = request.headers.get("x-forwarded-for")
    ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    return RequestMeta(
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


RequestMetaDep = Annotated[RequestMeta, Depends(get_request_meta)]
