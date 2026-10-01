"""Admin use-cases: overview metrics, user management, audit log queries.

Every mutating function writes an audit entry in the same transaction.
"""

import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.rbac import (
    ADMIN_ROLES,
    ROLE_DESCRIPTIONS,
    ROLE_PERMISSIONS,
    Permission,
    Role,
    highest_rank,
    permission_required_to_assign,
    permissions_for,
)
from app.db.models import AuditLog, User, UserRole, UserStatus
from app.db.models import Role as RoleModel
from app.modules.audit import service as audit
from app.modules.audit.service import RequestMeta
from app.modules.auth.service import ensure_roles, revoke_all_for_user


@dataclass(frozen=True, slots=True)
class Overview:
    total_users: int
    active_users_30d: int
    new_users_in_range: int
    suspended_users: int
    admin_users: int
    signups_by_day: list[tuple[str, int]]
    range_start: datetime
    range_end: datetime


async def get_overview(session: AsyncSession, start: datetime, end: datetime) -> Overview:
    now = datetime.now(UTC)
    total = await session.scalar(select(func.count()).select_from(User)) or 0
    active = (
        await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.last_login_at >= now - timedelta(days=30))
        )
        or 0
    )
    suspended = (
        await session.scalar(
            select(func.count()).select_from(User).where(User.status == UserStatus.SUSPENDED)
        )
        or 0
    )
    admins = (
        await session.scalar(
            select(func.count(func.distinct(UserRole.user_id)))
            .join(RoleModel, RoleModel.id == UserRole.role_id)
            .where(RoleModel.name.in_([r.value for r in ADMIN_ROLES]))
        )
        or 0
    )
    # Bucket by day in Python: portable across Postgres and SQLite, and the range is bounded.
    created = (
        await session.scalars(
            select(User.created_at).where(User.created_at >= start, User.created_at < end)
        )
    ).all()
    per_day = Counter(ts.date() for ts in created)
    days: list[tuple[str, int]] = []
    day: date = start.date()
    while day <= end.date():
        days.append((day.isoformat(), per_day.get(day, 0)))
        day += timedelta(days=1)

    return Overview(
        total_users=total,
        active_users_30d=active,
        new_users_in_range=len(created),
        suspended_users=suspended,
        admin_users=admins,
        signups_by_day=days,
        range_start=start,
        range_end=end,
    )


async def list_users(
    session: AsyncSession,
    *,
    search: str | None,
    role: Role | None,
    status: UserStatus | None,
    page: int,
    page_size: int,
) -> tuple[list[User], int]:
    query: Select[User] = select(User)
    if search:
        pattern = f"%{search.strip().lower()}%"
        query = query.where(
            or_(func.lower(User.email).like(pattern), func.lower(User.name).like(pattern))
        )
    if status:
        query = query.where(User.status == status)
    if role:
        query = query.where(
            User.id.in_(
                select(UserRole.user_id)
                .join(RoleModel, RoleModel.id == UserRole.role_id)
                .where(RoleModel.name == role.value)
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(User.created_at.desc(), User.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


def _guard_target(actor: User, target: User) -> None:
    if actor.id == target.id:
        raise ForbiddenError("You cannot change your own account here", code="self_modification")
    if highest_rank(target.role_names) > highest_rank(actor.role_names):
        raise ForbiddenError("You cannot modify a user with a higher role")


async def _count_super_admins(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(RoleModel, RoleModel.id == UserRole.role_id)
            .where(RoleModel.name == Role.SUPER_ADMIN.value)
        )
        or 0
    )


async def set_user_role(
    session: AsyncSession, *, actor: User, user_id: uuid.UUID, role: Role, meta: RequestMeta
) -> User:
    """Replace the user's role(s) with exactly one role."""
    target = await _get_user(session, user_id)
    _guard_target(actor, target)
    if permission_required_to_assign(role) not in permissions_for(actor.role_names):
        raise ForbiddenError(f"You cannot assign the '{role.value}' role")

    before = target.role_names
    if before == [role.value]:
        return target
    if Role.SUPER_ADMIN.value in before and await _count_super_admins(session) <= 1:
        raise ConflictError("Cannot demote the last super_admin", code="last_super_admin")

    roles = await ensure_roles(session)
    await session.execute(delete(UserRole).where(UserRole.user_id == target.id))
    session.add(UserRole(user_id=target.id, role_id=roles[role.value].id, granted_by_id=actor.id))
    await session.flush()
    await session.refresh(target, ["roles"])

    await audit.record(
        session,
        actor=actor,
        action="user.role_changed",
        target_type="user",
        target_id=target.id,
        before={"roles": before},
        after={"roles": target.role_names},
        meta=meta,
    )
    return target


async def set_user_status(
    session: AsyncSession,
    *,
    actor: User,
    user_id: uuid.UUID,
    status: UserStatus,
    reason: str | None,
    meta: RequestMeta,
) -> User:
    target = await _get_user(session, user_id)
    _guard_target(actor, target)
    if target.status == status:
        return target

    before = {"status": target.status.value, "reason": target.suspended_reason}
    target.status = status
    target.suspended_reason = reason if status == UserStatus.SUSPENDED else None
    if status == UserStatus.SUSPENDED:
        await revoke_all_for_user(session, target.id)
    await session.flush()

    await audit.record(
        session,
        actor=actor,
        action="user.suspended" if status == UserStatus.SUSPENDED else "user.unsuspended",
        target_type="user",
        target_id=target.id,
        before=before,
        after={"status": target.status.value, "reason": target.suspended_reason},
        meta=meta,
    )
    return target


async def list_audit_logs(
    session: AsyncSession,
    *,
    action: str | None,
    actor_email: str | None,
    target_id: str | None,
    start: datetime | None,
    end: datetime | None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    query: Select[AuditLog] = select(AuditLog)
    if action:
        query = query.where(AuditLog.action.startswith(action))
    if actor_email:
        query = query.where(func.lower(AuditLog.actor_email).like(f"%{actor_email.lower()}%"))
    if target_id:
        query = query.where(AuditLog.target_id == target_id)
    if start:
        query = query.where(AuditLog.created_at >= start)
    if end:
        query = query.where(AuditLog.created_at < end)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.order_by(AuditLog.created_at.desc(), AuditLog.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(rows), total


def describe_roles() -> list[tuple[Role, str, list[Permission]]]:
    return [(role, ROLE_DESCRIPTIONS[role], sorted(ROLE_PERMISSIONS[role])) for role in Role]
