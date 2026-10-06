"""Sign-in, token issuing and refresh-token rotation."""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError, ForbiddenError, UnauthorizedError
from app.core.passwords import dummy_hash, hash_password, verify_password
from app.core.rbac import ROLE_DESCRIPTIONS, Role
from app.core.security import create_token, decode_token
from app.db.models import RefreshToken, User, UserRole
from app.db.models import Role as RoleModel
from app.modules.audit import service as audit
from app.modules.audit.service import RequestMeta

logger = structlog.stdlib.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str
    access_expires_at: datetime
    refresh_expires_at: datetime
    refresh_jti: uuid.UUID


async def ensure_roles(session: AsyncSession) -> dict[str, RoleModel]:
    """Make sure every known role row exists. Idempotent; the migration seeds them too."""
    existing = {r.name: r for r in (await session.scalars(select(RoleModel))).all()}
    for role in Role:
        if role.value not in existing:
            row = RoleModel(name=role.value, description=ROLE_DESCRIPTIONS[role])
            session.add(row)
            existing[role.value] = row
    await session.flush()
    return existing


async def _grant(
    session: AsyncSession, user: User, role: Role, granted_by: User | None = None
) -> bool:
    roles = await ensure_roles(session)
    role_row = roles[role.value]
    already = await session.get(UserRole, (user.id, role_row.id))
    if already:
        return False
    session.add(
        UserRole(
            user_id=user.id,
            role_id=role_row.id,
            granted_by_id=granted_by.id if granted_by else None,
        )
    )
    await session.flush()
    return True


async def sign_in(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    name: str | None,
    avatar_url: str | None,
    google_sub: str | None,
    meta: RequestMeta,
) -> tuple[User, TokenPair]:
    """Find-or-create the user, apply the admin allowlist, and issue tokens."""
    email = email.lower()
    user: User | None = None
    if google_sub:
        user = await session.scalar(select(User).where(User.google_sub == google_sub))
    if user is None:
        user = await session.scalar(select(User).where(User.email == email))

    created = user is None
    if user is None:
        user = User(email=email, name=name, avatar_url=avatar_url, google_sub=google_sub)
        session.add(user)
        await session.flush()
        await _grant(session, user, Role.USER)
    else:
        if google_sub and user.google_sub is None:
            # Google proved ownership of the email; drop any password someone else may have set
            # by registering it first (registration doesn't verify emails).
            user.password_hash = None
        user.email = email
        user.name = user.name or name
        user.avatar_url = avatar_url or user.avatar_url
        user.google_sub = user.google_sub or google_sub

    return await _complete_sign_in(session, settings, user, email=email, meta=meta, created=created)


async def register(
    session: AsyncSession,
    settings: Settings,
    *,
    email: str,
    name: str | None,
    password: str,
    meta: RequestMeta,
) -> tuple[User, TokenPair]:
    """Create an email + password account and sign it in."""
    email = email.lower()
    # Emails aren't verified, so allowlisted admin emails can't be claimed by registering.
    if email in settings.admin_emails:
        raise ForbiddenError("This email can't be registered here", code="registration_blocked")
    if await session.scalar(select(User.id).where(User.email == email)):
        raise ConflictError(
            "An account with this email already exists. Sign in instead.", code="email_taken"
        )
    password_hash = await asyncio.to_thread(hash_password, password)
    user = User(email=email, name=name, password_hash=password_hash)
    session.add(user)
    await session.flush()
    await _grant(session, user, Role.USER)
    return await _complete_sign_in(session, settings, user, email=email, meta=meta, created=True)


async def password_sign_in(
    session: AsyncSession, settings: Settings, *, email: str, password: str, meta: RequestMeta
) -> tuple[User, TokenPair]:
    email = email.lower()
    user = await session.scalar(select(User).where(User.email == email))
    stored = user.password_hash if user else None
    valid = await asyncio.to_thread(verify_password, password, stored or dummy_hash())
    if user is None or stored is None or not valid:
        raise UnauthorizedError("Wrong email or password", code="invalid_credentials")
    return await _complete_sign_in(session, settings, user, email=email, meta=meta, created=False)


async def _complete_sign_in(
    session: AsyncSession,
    settings: Settings,
    user: User,
    *,
    email: str,
    meta: RequestMeta,
    created: bool,
) -> tuple[User, TokenPair]:
    """Suspension check, admin allowlist, and fresh tokens."""
    if not user.is_active:
        raise ForbiddenError("This account is suspended", code="account_suspended")

    # Allowlist is the only bootstrap path to admin; everything else goes through a super_admin.
    if email in settings.admin_emails and await _grant(session, user, Role.SUPER_ADMIN):
        await audit.record(
            session,
            actor=None,
            action="user.role_granted",
            target_type="user",
            target_id=user.id,
            after={"role": Role.SUPER_ADMIN.value, "source": "ADMIN_EMAILS allowlist"},
            meta=meta,
        )

    user.last_login_at = datetime.now(UTC)
    await session.flush()
    await session.refresh(user, ["roles"])
    tokens = await issue_tokens(session, settings, user, user_agent=meta.user_agent)
    logger.info("user_signed_in", user_id=str(user.id), created=created)
    return user, tokens


async def issue_tokens(
    session: AsyncSession, settings: Settings, user: User, *, user_agent: str | None
) -> TokenPair:
    access = create_token(settings, user.id, "access")
    refresh = create_token(settings, user.id, "refresh")
    session.add(
        RefreshToken(
            id=refresh.claims.jti,
            user_id=user.id,
            expires_at=refresh.claims.expires_at,
            user_agent=(user_agent or "")[:500] or None,
        )
    )
    await session.flush()
    return TokenPair(
        access_token=access.token,
        refresh_token=refresh.token,
        access_expires_at=access.claims.expires_at,
        refresh_expires_at=refresh.claims.expires_at,
        refresh_jti=refresh.claims.jti,
    )


async def rotate_refresh_token(
    session: AsyncSession, settings: Settings, raw_token: str, *, user_agent: str | None
) -> tuple[User, TokenPair]:
    claims = decode_token(settings, raw_token, "refresh")
    stored = await session.get(RefreshToken, claims.jti, with_for_update=True)
    if stored is None or stored.user_id != claims.subject:
        raise UnauthorizedError("Invalid refresh token", code="invalid_token")

    in_grace = stored.revoked_at is not None and await _within_reuse_grace(
        session, settings, stored
    )
    if stored.revoked_at is not None and not in_grace:
        # A revoked token came back: assume it was stolen and cut off every session.
        await revoke_all_for_user(session, stored.user_id)
        # Commit now: the error below makes the request dependency roll back.
        await session.commit()
        logger.warning("refresh_token_reuse_detected", user_id=str(stored.user_id))
        raise UnauthorizedError("Refresh token reuse detected", code="token_reused")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Account unavailable", code="account_unavailable")

    pair = await issue_tokens(session, settings, user, user_agent=user_agent)
    if not in_grace:
        stored.revoked_at = datetime.now(UTC)
        stored.replaced_by_id = pair.refresh_jti
    await session.flush()
    return user, pair


async def _within_reuse_grace(
    session: AsyncSession, settings: Settings, stored: RefreshToken
) -> bool:
    """Allow a just-rotated token to be presented again for a few seconds.

    Parallel requests (several tabs, or server renders that cannot persist the new
    cookie) often refresh with the same token at once. Without a grace window the
    second one would look like theft and log the user out everywhere. Tokens that
    were revoked by logout or a family revocation never qualify.
    """
    if stored.revoked_at is None or stored.replaced_by_id is None:
        return False
    revoked_at = stored.revoked_at.replace(tzinfo=stored.revoked_at.tzinfo or UTC)
    age = (datetime.now(UTC) - revoked_at).total_seconds()
    if age > settings.refresh_reuse_grace_seconds:
        return False
    replacement = await session.get(RefreshToken, stored.replaced_by_id)
    # The replacement must still be alive (or itself have been rotated normally).
    return replacement is not None and (
        replacement.revoked_at is None or replacement.replaced_by_id is not None
    )


async def revoke_refresh_token(session: AsyncSession, settings: Settings, raw_token: str) -> None:
    try:
        claims = decode_token(settings, raw_token, "refresh")
    except UnauthorizedError:
        return  # logging out with a bad token is a no-op, not an error
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.id == claims.jti, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )


async def revoke_all_for_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
