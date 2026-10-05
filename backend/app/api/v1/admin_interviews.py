"""Admin: interview types (settings and rubrics) and an overview of all interviews."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import RequestMetaDep, SessionDep, require_permission
from app.api.v1.interview_schemas import (
    AdminInterviewOut,
    InterviewTypeAdmin,
    InterviewTypeUpdate,
)
from app.api.v1.schemas import Page
from app.core.errors import AppError, ErrorResponse, NotFoundError
from app.core.rbac import Permission
from app.db.models import Interview, InterviewReport, InterviewStatus, InterviewType, User
from app.modules.audit import service as audit
from app.modules.interviews import planning, service

router = APIRouter(
    prefix="/admin",
    tags=["admin: interviews"],
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)

InterviewsAdmin = Annotated[User, Depends(require_permission(Permission.INTERVIEWS_MANAGE))]
_AUDITED = (
    "name",
    "description",
    "enabled",
    "duration_minutes",
    "question_count",
    "max_followups",
    "difficulty",
    "rubric",
)


def _snapshot(t: InterviewType) -> dict[str, Any]:
    return {f: (getattr(t, f).value if f == "difficulty" else getattr(t, f)) for f in _AUDITED}


@router.get("/interview-types", response_model=list[InterviewTypeAdmin])
async def list_types(session: SessionDep, _: InterviewsAdmin) -> list[InterviewTypeAdmin]:
    types = await service.list_types(session, enabled_only=False)
    await session.commit()
    return [InterviewTypeAdmin.model_validate(t) for t in types]


@router.patch(
    "/interview-types/{key}",
    response_model=InterviewTypeAdmin,
    responses={400: {"model": ErrorResponse}},
)
async def update_type(
    key: str,
    body: InterviewTypeUpdate,
    session: SessionDep,
    actor: InterviewsAdmin,
    meta: RequestMetaDep,
) -> InterviewTypeAdmin:
    """Changes apply to interviews started afterwards; running ones keep their settings."""
    await service.ensure_types(session)
    type_ = await session.get(InterviewType, key)
    if type_ is None:
        raise NotFoundError("Interview type not found")
    changes = body.model_dump(exclude_unset=True)
    available = len(planning.bank().get(key, []))
    if (
        "question_count" in changes
        and key in planning.KIND_FOR_TYPE
        and changes["question_count"] > available
    ):
        raise AppError(
            f"The question bank has only {available} {type_.name} questions.",
            code="not_enough_questions",
        )
    before = _snapshot(type_)
    for field, value in changes.items():
        if field == "rubric":
            value = [c if isinstance(c, dict) else c.model_dump() for c in value]
        setattr(type_, field, value)
    after = _snapshot(type_)
    if before != after:
        await audit.record(
            session,
            actor=actor,
            action="interview_type.updated",
            target_type="interview_type",
            target_id=key,
            before={k: v for k, v in before.items() if before[k] != after[k]},
            after={k: v for k, v in after.items() if before[k] != after[k]},
            meta=meta,
        )
    await session.commit()
    await session.refresh(type_)
    return InterviewTypeAdmin.model_validate(type_)


@router.get("/interviews", response_model=Page[AdminInterviewOut])
async def list_interviews(
    session: SessionDep,
    _: InterviewsAdmin,
    status: InterviewStatus | None = None,
    type_key: Annotated[str | None, Query(max_length=30)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AdminInterviewOut]:
    """Every user's interviews, newest first (for spotting problems; transcripts stay private)."""
    stmt = (
        select(Interview, User.email, InterviewReport)
        .join(User, User.id == Interview.user_id)
        .outerjoin(InterviewReport, InterviewReport.interview_id == Interview.id)
    )
    if status:
        stmt = stmt.where(Interview.status == status)
    if type_key:
        stmt = stmt.where(Interview.type_key == type_key)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.execute(
        stmt.order_by(Interview.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        AdminInterviewOut(
            id=i.id,
            user_email=email,
            type_key=i.type_key,
            status=i.status,
            difficulty=i.difficulty,
            job_title=i.job_title,
            created_at=i.created_at,
            ended_at=i.ended_at,
            end_reason=i.end_reason,
            hints_used=i.hints_used,
            report_status=r.status if r else None,
            overall_score=r.overall_score if r else None,
        )
        for i, email, r in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)
