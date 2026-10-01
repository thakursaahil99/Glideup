"""Admin console API. Every route checks a permission on the server; the UI hiding
a button is a convenience, not a control."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import RequestMetaDep, SessionDep, require_permission
from app.api.v1.resumes import to_out, to_summary
from app.api.v1.schemas import (
    AdminOverview,
    AdminUserDetail,
    AuditLogOut,
    DailyCount,
    Page,
    RoleOut,
    SetRoleRequest,
    SetStatusRequest,
    UserSummary,
)
from app.api.v1.users import to_profile_out
from app.core.errors import AppError, ErrorResponse
from app.core.rbac import Permission, Role
from app.db.models import User, UserStatus
from app.modules.admin import service

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

MAX_RANGE_DAYS = 366


def _as_utc(value: datetime | None) -> datetime | None:
    # Query strings may omit the offset; treat naive timestamps as UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


@router.get("/overview", response_model=AdminOverview)
async def overview(
    session: SessionDep,
    _: Annotated[User, Depends(require_permission(Permission.ADMIN_ACCESS))],
    start: datetime | None = None,
    end: datetime | None = None,
) -> AdminOverview:
    range_end = _as_utc(end) or datetime.now(UTC)
    range_start = _as_utc(start) or range_end - timedelta(days=29)
    if range_start >= range_end or (range_end - range_start).days > MAX_RANGE_DAYS:
        raise AppError(
            f"Date range must be positive and at most {MAX_RANGE_DAYS} days", code="invalid_range"
        )
    data = await service.get_overview(session, range_start, range_end)
    return AdminOverview(
        total_users=data.total_users,
        active_users_30d=data.active_users_30d,
        new_users_in_range=data.new_users_in_range,
        suspended_users=data.suspended_users,
        admin_users=data.admin_users,
        signups_by_day=[DailyCount(date=d, count=c) for d, c in data.signups_by_day],
        range_start=data.range_start,
        range_end=data.range_end,
        resumes_uploaded=data.resumes_uploaded,
        resumes_parsed=data.resumes_parsed,
        resumes_failed=data.resumes_failed,
        llm_calls=data.llm_calls,
        llm_failed_calls=data.llm_failed_calls,
        llm_tokens=data.llm_tokens,
        llm_estimated_cost_usd=float(data.llm_estimated_cost_usd),
    )


@router.get("/users", response_model=Page[UserSummary])
async def list_users(
    session: SessionDep,
    _: Annotated[User, Depends(require_permission(Permission.USERS_READ))],
    search: Annotated[str | None, Query(max_length=200)] = None,
    role: Role | None = None,
    status: UserStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[UserSummary]:
    users, total = await service.list_users(
        session, search=search, role=role, status=status, page=page, page_size=page_size
    )
    return Page(
        items=[UserSummary.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=AdminUserDetail)
async def get_user(
    user_id: uuid.UUID,
    session: SessionDep,
    meta: RequestMetaDep,
    actor: Annotated[User, Depends(require_permission(Permission.USERS_READ))],
) -> AdminUserDetail:
    detail = await service.get_user_detail(session, actor=actor, user_id=user_id, meta=meta)
    active = next((r for r in detail.resumes if r.is_active), None)
    return AdminUserDetail(
        user=UserSummary.model_validate(detail.user),
        suspended_reason=detail.user.suspended_reason,
        profile=to_profile_out(detail.user, detail.profile, has_resume=active is not None)
        if detail.profile
        else None,
        resumes=[to_summary(r) for r in detail.resumes],
        active_resume=to_out(active) if active else None,
        llm_calls=detail.llm_calls,
    )


@router.put("/users/{user_id}/role", response_model=UserSummary)
async def set_role(
    user_id: uuid.UUID,
    body: SetRoleRequest,
    session: SessionDep,
    meta: RequestMetaDep,
    actor: Annotated[User, Depends(require_permission(Permission.ROLES_ASSIGN))],
) -> UserSummary:
    user = await service.set_user_role(
        session, actor=actor, user_id=user_id, role=body.role, meta=meta
    )
    return UserSummary.model_validate(user)


@router.put("/users/{user_id}/status", response_model=UserSummary)
async def set_status(
    user_id: uuid.UUID,
    body: SetStatusRequest,
    session: SessionDep,
    meta: RequestMetaDep,
    actor: Annotated[User, Depends(require_permission(Permission.USERS_WRITE))],
) -> UserSummary:
    user = await service.set_user_status(
        session, actor=actor, user_id=user_id, status=body.status, reason=body.reason, meta=meta
    )
    return UserSummary.model_validate(user)


@router.get("/roles", response_model=list[RoleOut])
async def list_roles(
    _: Annotated[User, Depends(require_permission(Permission.ADMIN_ACCESS))],
) -> list[RoleOut]:
    return [
        RoleOut(name=role.value, description=description, permissions=[p.value for p in perms])
        for role, description, perms in service.describe_roles()
    ]


@router.get("/audit-logs", response_model=Page[AuditLogOut])
async def list_audit_logs(
    session: SessionDep,
    _: Annotated[User, Depends(require_permission(Permission.AUDIT_READ))],
    action: Annotated[str | None, Query(max_length=100)] = None,
    actor_email: Annotated[str | None, Query(max_length=320)] = None,
    target_id: Annotated[str | None, Query(max_length=100)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[AuditLogOut]:
    logs, total = await service.list_audit_logs(
        session,
        action=action,
        actor_email=actor_email,
        target_id=target_id,
        start=_as_utc(start),
        end=_as_utc(end),
        page=page,
        page_size=page_size,
    )
    return Page(
        items=[AuditLogOut.model_validate(log) for log in logs],
        total=total,
        page=page,
        page_size=page_size,
    )
