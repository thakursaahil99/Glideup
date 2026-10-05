"""Framework tests, skill scores and badges (users), and framework settings (admin)."""

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.api.deps import CurrentUser, RequestMetaDep, SessionDep, require_permission
from app.core.errors import ErrorResponse, NotFoundError
from app.core.rbac import Permission
from app.db.models import AttemptStatus, Framework, FrameworkAttempt, User
from app.modules.audit import service as audit
from app.modules.skills import service
from app.modules.skills.content import FRAMEWORK_TYPES

router = APIRouter(
    tags=["skills"], responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)


class FrameworkOut(BaseModel):
    key: str
    name: str
    description: str
    duration_minutes: int
    questions: int
    best_score: int | None


class AttemptQuestion(BaseModel):
    id: str
    type: str
    title: str
    statement: str
    content: dict[str, Any]
    result: dict[str, Any] | None = None  # after grading


class AttemptOut(BaseModel):
    id: uuid.UUID
    framework_key: str
    framework_name: str
    status: AttemptStatus
    ends_at: datetime
    answers: dict[str, Any]
    questions: list[AttemptQuestion]
    score: int | None
    level: str | None
    sections: dict[str, Any]
    error: str | None


class AnswersIn(BaseModel):
    answers: dict[str, int | str | None] = Field(max_length=30)


class SkillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    skill: str
    kind: str
    score: int
    level: str
    updated_at: datetime


class BadgeOut(BaseModel):
    key: str
    name: str
    description: str
    awarded_at: datetime


class SkillsOverview(BaseModel):
    skills: list[SkillOut]
    badges: list[BadgeOut]


async def _attempt_out(session: SessionDep, attempt: FrameworkAttempt) -> AttemptOut:
    framework = await session.get(Framework, attempt.framework_key)
    questions = await service.attempt_questions(session, attempt)
    graded = attempt.status == AttemptStatus.GRADED
    return AttemptOut(
        id=attempt.id,
        framework_key=attempt.framework_key,
        framework_name=framework.name if framework else attempt.framework_key,
        status=attempt.status,
        ends_at=attempt.ends_at,
        answers=attempt.answers or {},
        questions=[
            AttemptQuestion(
                **service.question_view(q, reveal=graded),
                result=(attempt.results or {}).get(str(q.id)) if graded else None,
            )
            for q in questions
        ],
        score=attempt.score,
        level=attempt.level,
        sections=attempt.sections or {},
        error=attempt.error,
    )


@router.get("/frameworks", response_model=list[FrameworkOut])
async def frameworks(session: SessionDep, user: CurrentUser) -> list[FrameworkOut]:
    return [
        FrameworkOut(
            key=f.key,
            name=f.name,
            description=f.description,
            duration_minutes=f.duration_minutes,
            questions=count,
            best_score=best,
        )
        for f, count, best in await service.list_frameworks(session, user)
    ]


@router.post(
    "/frameworks/{key}/attempts",
    response_model=AttemptOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def start(key: str, session: SessionDep, user: CurrentUser) -> AttemptOut:
    """Start a timed test (or resume the open one)."""
    await service.seed_frameworks(session)
    attempt = await service.start_attempt(session, user, key)
    return await _attempt_out(session, attempt)


@router.get("/framework-attempts/{attempt_id}", response_model=AttemptOut)
async def get_attempt(attempt_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> AttemptOut:
    return await _attempt_out(session, await service.get_attempt(session, user, attempt_id))


@router.put(
    "/framework-attempts/{attempt_id}/answers",
    response_model=AttemptOut,
    responses={409: {"model": ErrorResponse}},
)
async def save_answers(
    attempt_id: uuid.UUID, body: AnswersIn, session: SessionDep, user: CurrentUser
) -> AttemptOut:
    """Autosave: merges the given answers into the attempt."""
    attempt = await service.save_answers(session, user, attempt_id, body.answers)
    return await _attempt_out(session, attempt)


@router.post(
    "/framework-attempts/{attempt_id}/submit",
    response_model=AttemptOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def submit(attempt_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> AttemptOut:
    """Grade in the background (poll until `graded`). Safe to repeat."""
    attempt = await service.submit_attempt(session, user, attempt_id)
    return await _attempt_out(session, attempt)


@router.get("/me/skills", response_model=SkillsOverview)
async def my_skills(session: SessionDep, user: CurrentUser) -> SkillsOverview:
    scores, badges = await service.skills_overview(session, user)
    return SkillsOverview(
        skills=[SkillOut.model_validate(s) for s in scores],
        badges=[
            BadgeOut(key=b.badge, name=d.name, description=d.description, awarded_at=b.awarded_at)
            for b, d in badges
        ],
    )


# ------------------------------------------------------------------ admin

FrameworksAdmin = Annotated[User, Depends(require_permission(Permission.QUESTIONS_MANAGE))]


class FrameworkAdmin(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    key: str
    name: str
    language_key: str
    description: str
    enabled: bool
    duration_minutes: int
    composition: dict[str, int]


class FrameworkUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    description: str | None = Field(default=None, max_length=500)
    enabled: bool | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=180)
    composition: dict[str, int] | None = None

    @field_validator("composition")
    @classmethod
    def _composition(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return value
        if set(value) - set(FRAMEWORK_TYPES) or any(not 0 <= n <= 20 for n in value.values()):
            raise ValueError(f"Use only {', '.join(FRAMEWORK_TYPES)} with 0-20 questions each")
        if not sum(value.values()):
            raise ValueError("A test needs at least one question")
        return value


@router.get("/admin/frameworks", response_model=list[FrameworkAdmin], tags=["admin: question bank"])
async def admin_frameworks(session: SessionDep, _: FrameworksAdmin) -> list[FrameworkAdmin]:
    from sqlalchemy import select

    await service.seed_frameworks(session)
    await session.commit()
    return [
        FrameworkAdmin.model_validate(f)
        for f in await session.scalars(select(Framework).order_by(Framework.name))
    ]


@router.patch(
    "/admin/frameworks/{key}", response_model=FrameworkAdmin, tags=["admin: question bank"]
)
async def update_framework(
    key: str,
    body: FrameworkUpdate,
    session: SessionDep,
    actor: FrameworksAdmin,
    meta: RequestMetaDep,
) -> FrameworkAdmin:
    framework = await session.get(Framework, key)
    if framework is None:
        raise NotFoundError("Framework not found")
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(framework, k) for k in changes}
    for field, value in changes.items():
        setattr(framework, field, value)
    await audit.record(
        session,
        actor=actor,
        action="framework.updated",
        target_type="framework",
        target_id=key,
        before=before,
        after=changes,
        meta=meta,
    )
    await session.commit()
    return FrameworkAdmin.model_validate(framework)
