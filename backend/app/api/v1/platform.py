"""Feature flags, AI/LLM settings, system health and announcements (admin), plus the user
side: the flags that apply to me and active announcements."""

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, RequestMetaDep, SessionDep, require_permission
from app.core.errors import ErrorResponse, NotFoundError
from app.core.rbac import Permission, permissions_for
from app.db.models import Announcement, FeatureFlag, User
from app.llm import runtime
from app.llm.routing import DEFAULT_ROUTES
from app.modules.audit import service as audit
from app.modules.platform import service

router = APIRouter(tags=["platform"], responses={401: {"model": ErrorResponse}})

FlagsAdmin = Annotated[User, Depends(require_permission(Permission.FLAGS_MANAGE))]
LLMAdmin = Annotated[User, Depends(require_permission(Permission.LLM_MANAGE))]
SystemReader = Annotated[User, Depends(require_permission(Permission.SYSTEM_READ))]
AnnouncementsAdmin = Annotated[User, Depends(require_permission(Permission.ANNOUNCEMENTS_MANAGE))]
SystemManager = Annotated[User, Depends(require_permission(Permission.SYSTEM_MANAGE))]


# ------------------------------------------------------------------ user side


class AnnouncementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    body: str
    level: str
    audience: str
    starts_at: datetime | None
    ends_at: datetime | None
    active: bool
    created_at: datetime


@router.get("/me/flags", response_model=dict[str, bool])
async def my_flags(session: SessionDep, user: CurrentUser) -> dict[str, bool]:
    """Which optional features are on for me (the UI hides what's off)."""
    return await service.flags_for(session, user.id)


@router.get("/announcements", response_model=list[AnnouncementOut])
async def announcements(session: SessionDep, user: CurrentUser) -> list[AnnouncementOut]:
    is_admin = Permission.ADMIN_ACCESS in permissions_for(user.role_names)
    return [
        AnnouncementOut.model_validate(a)
        for a in await service.active_announcements(session, is_admin=is_admin)
    ]


# ------------------------------------------------------------------ feature flags


class FlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    description: str
    enabled: bool
    rollout_percent: int
    allow_user_ids: list[str]
    updated_at: datetime


class FlagUpdate(BaseModel):
    enabled: bool | None = None
    rollout_percent: int | None = Field(default=None, ge=0, le=100)
    allow_user_ids: list[uuid.UUID] | None = Field(default=None, max_length=200)


@router.get("/admin/flags", response_model=list[FlagOut], tags=["admin: platform"])
async def list_flags(session: SessionDep, _: FlagsAdmin) -> list[FlagOut]:
    await service.ensure_flags(session)
    await session.commit()
    return [
        FlagOut.model_validate(f)
        for f in await session.scalars(select(FeatureFlag).order_by(FeatureFlag.key))
    ]


@router.patch("/admin/flags/{key}", response_model=FlagOut, tags=["admin: platform"])
async def update_flag(
    key: str, body: FlagUpdate, session: SessionDep, actor: FlagsAdmin, meta: RequestMetaDep
) -> FlagOut:
    await service.ensure_flags(session)
    flag = await session.get(FeatureFlag, key)
    if flag is None:
        raise NotFoundError("Flag not found")
    changes = body.model_dump(exclude_unset=True)
    if "allow_user_ids" in changes:
        changes["allow_user_ids"] = [str(u) for u in changes["allow_user_ids"] or []]
    before = {k: getattr(flag, k) for k in changes}
    for field_name, value in changes.items():
        setattr(flag, field_name, value)
    await audit.record(
        session,
        actor=actor,
        action="flag.updated",
        target_type="feature_flag",
        target_id=key,
        before=before,
        after=changes,
        meta=meta,
    )
    await session.commit()
    await session.refresh(flag)
    service.invalidate_flags()
    return FlagOut.model_validate(flag)


# ------------------------------------------------------------------ AI / LLM settings


class LLMSettingsOut(BaseModel):
    settings: dict[str, Any]
    effective_routes: dict[str, list[str]]
    providers: list[str]  # configured on this deployment
    tasks: list[str]


class LLMSettingsUpdate(BaseModel):
    values: dict[str, Any] = Field(max_length=10)


@router.get("/admin/llm/settings", response_model=LLMSettingsOut, tags=["admin: platform"])
async def llm_settings(session: SessionDep, _: LLMAdmin) -> LLMSettingsOut:
    runtime.apply(await service.current_settings(session))
    return LLMSettingsOut(
        settings=await service.current_settings(session),
        effective_routes=service.effective_routes(),
        providers=service.known_providers(),
        tasks=sorted(DEFAULT_ROUTES),
    )


@router.put(
    "/admin/llm/settings",
    response_model=LLMSettingsOut,
    responses={400: {"model": ErrorResponse}},
    tags=["admin: platform"],
)
async def update_llm_settings(
    body: LLMSettingsUpdate, session: SessionDep, actor: LLMAdmin, meta: RequestMetaDep
) -> LLMSettingsOut:
    """Routing per task (fallback order), cache on/off and TTL, per-user daily token budget.
    Takes effect on every worker within 30 seconds."""
    clean = service.validate_settings(body.values)
    before = {k: v for k, v in (await service.current_settings(session)).items() if k in clean}
    merged = await service.save_settings(session, clean)
    await audit.record(
        session,
        actor=actor,
        action="llm.settings_updated",
        target_type="llm_settings",
        before=before,
        after=clean,
        meta=meta,
    )
    await session.commit()
    return LLMSettingsOut(
        settings=merged,
        effective_routes=service.effective_routes(),
        providers=service.known_providers(),
        tasks=sorted(DEFAULT_ROUTES),
    )


@router.get("/admin/llm/usage", response_model=list[dict[str, Any]], tags=["admin: platform"])
async def llm_usage(
    session: SessionDep, _: LLMAdmin, days: Annotated[int, Query(ge=1, le=90)] = 7
) -> list[dict[str, Any]]:
    """Calls, errors, cache hits, tokens, cost and latency per provider, model and task."""
    return await service.usage_report(session, days)


# ------------------------------------------------------------------ system health


class CheckOut(BaseModel):
    name: str
    status: Literal["ok", "degraded", "down", "off"]
    detail: str
    latency_ms: int | None
    extra: dict[str, Any]


class FailedJobOut(BaseModel):
    kind: str
    id: str
    label: str
    error: str | None
    at: datetime | None


class HealthOut(BaseModel):
    checks: list[CheckOut]
    failed_jobs: list[FailedJobOut]
    grafana_url: str | None


@router.get("/admin/system/health", response_model=HealthOut, tags=["admin: platform"])
async def system_health(session: SessionDep, _: SystemReader) -> HealthOut:
    from app.core.config import get_settings

    checks = await service.system_health(session)
    return HealthOut(
        checks=[
            CheckOut(
                name=c.name,
                status=c.status,
                detail=c.detail,
                latency_ms=c.latency_ms,
                extra=c.extra,
            )
            for c in checks
        ],
        failed_jobs=[FailedJobOut(**j) for j in await service.failed_jobs(session)],
        grafana_url=get_settings().grafana_url,
    )


@router.post(
    "/admin/system/jobs/{kind}/{item_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    tags=["admin: platform"],
    responses={404: {"model": ErrorResponse}},
)
async def retry_failed_job(
    kind: str, item_id: str, session: SessionDep, actor: SystemManager, meta: RequestMetaDep
) -> dict[str, str]:
    await audit.record(
        session,
        actor=actor,
        action="system.job_retried",
        target_type=kind,
        target_id=item_id,
        meta=meta,
    )
    await session.commit()
    await service.retry_job(session, kind, item_id)
    return {"status": "queued"}


# ------------------------------------------------------------------ announcements


class AnnouncementIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(default="", max_length=2000)
    level: Literal["info", "warning"] = "info"
    audience: Literal["all", "admins"] = "all"
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    active: bool = True


@router.get("/admin/announcements", response_model=list[AnnouncementOut], tags=["admin: platform"])
async def admin_announcements(session: SessionDep, _: AnnouncementsAdmin) -> list[AnnouncementOut]:
    rows = await session.scalars(
        select(Announcement).order_by(Announcement.created_at.desc()).limit(100)
    )
    return [AnnouncementOut.model_validate(a) for a in rows]


@router.post(
    "/admin/announcements",
    response_model=AnnouncementOut,
    status_code=status.HTTP_201_CREATED,
    tags=["admin: platform"],
)
async def create_announcement(
    body: AnnouncementIn, session: SessionDep, actor: AnnouncementsAdmin, meta: RequestMetaDep
) -> AnnouncementOut:
    announcement = Announcement(**body.model_dump(), created_by_id=actor.id)
    session.add(announcement)
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="announcement.created",
        target_type="announcement",
        target_id=announcement.id,
        after={"title": body.title, "audience": body.audience},
        meta=meta,
    )
    await session.commit()
    return AnnouncementOut.model_validate(announcement)


@router.patch(
    "/admin/announcements/{announcement_id}",
    response_model=AnnouncementOut,
    tags=["admin: platform"],
)
async def update_announcement(
    announcement_id: uuid.UUID,
    body: AnnouncementIn,
    session: SessionDep,
    actor: AnnouncementsAdmin,
    meta: RequestMetaDep,
) -> AnnouncementOut:
    announcement = await session.get(Announcement, announcement_id)
    if announcement is None:
        raise NotFoundError("Announcement not found")
    for field_name, value in body.model_dump().items():
        setattr(announcement, field_name, value)
    await audit.record(
        session,
        actor=actor,
        action="announcement.updated",
        target_type="announcement",
        target_id=announcement.id,
        after={"active": body.active, "title": body.title},
        meta=meta,
    )
    await session.commit()
    await session.refresh(announcement)
    return AnnouncementOut.model_validate(announcement)
