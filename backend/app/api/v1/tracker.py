"""Application tracker, reminders, the dashboard, and user reports (+ admin queue)."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import func, select

from app.api.deps import CurrentUser, RequestMetaDep, SessionDep, require_permission
from app.api.v1.schemas import Page
from app.core.errors import ErrorResponse, NotFoundError
from app.core.rbac import Permission
from app.db.models import ApplicationStatus, ReportKind, ReportState, User, UserReport
from app.modules.audit import service as audit
from app.modules.dashboard import service as dashboard
from app.modules.tracker import service

router = APIRouter(
    tags=["tracker"], responses={401: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}
)


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    from_status: str | None
    to_status: str | None
    note: str | None
    created_at: datetime


class ApplicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID | None
    company: str
    title: str
    url: str | None
    location: str | None
    status: ApplicationStatus
    position: int
    applied_at: datetime | None
    salary: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    events: list[EventOut]


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID | None = None
    company: str | None = Field(default=None, max_length=200)
    title: str | None = Field(default=None, max_length=300)
    url: HttpUrl | None = None
    location: str | None = Field(default=None, max_length=300)
    status: ApplicationStatus = ApplicationStatus.SAVED
    notes: str | None = Field(default=None, max_length=5000)


class ApplicationUpdate(BaseModel):
    status: ApplicationStatus | None = None
    position: int | None = Field(default=None, ge=0, le=10_000)
    notes: str | None = Field(default=None, max_length=5000)
    salary: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=2000, description="Adds a timeline note")


class ReminderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID | None
    title: str
    due_at: datetime
    done: bool


class ReminderCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_at: datetime
    application_id: uuid.UUID | None = None


class ReminderUpdate(BaseModel):
    done: bool | None = None
    due_at: datetime | None = None


@router.get("/applications", response_model=list[ApplicationOut])
async def applications(session: SessionDep, user: CurrentUser) -> list[ApplicationOut]:
    return [
        ApplicationOut.model_validate(a) for a in await service.list_applications(session, user)
    ]


@router.post(
    "/applications",
    response_model=ApplicationOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
async def create_application(
    body: ApplicationCreate, session: SessionDep, user: CurrentUser
) -> ApplicationOut:
    """Track a job from the board (`job_id`) or one found elsewhere (company + title)."""
    application = await service.create_application(
        session,
        user,
        job_id=body.job_id,
        company=body.company,
        title=body.title,
        url=str(body.url) if body.url else None,
        location=body.location,
        status=body.status,
        notes=body.notes,
    )
    return ApplicationOut.model_validate(application)


@router.patch("/applications/{application_id}", response_model=ApplicationOut)
async def update_application(
    application_id: uuid.UUID, body: ApplicationUpdate, session: SessionDep, user: CurrentUser
) -> ApplicationOut:
    application = await service.update_application(
        session, user, application_id, **body.model_dump(exclude_unset=True)
    )
    return ApplicationOut.model_validate(application)


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    application_id: uuid.UUID, session: SessionDep, user: CurrentUser
) -> None:
    await service.delete_application(session, user, application_id)


@router.get("/reminders", response_model=list[ReminderOut])
async def reminders(
    session: SessionDep, user: CurrentUser, include_done: bool = False
) -> list[ReminderOut]:
    return [
        ReminderOut.model_validate(r)
        for r in await service.list_reminders(session, user, include_done=include_done)
    ]


@router.post("/reminders", response_model=ReminderOut, status_code=status.HTTP_201_CREATED)
async def create_reminder(
    body: ReminderCreate, session: SessionDep, user: CurrentUser
) -> ReminderOut:
    due = body.due_at if body.due_at.tzinfo else body.due_at.replace(tzinfo=UTC)
    reminder = await service.create_reminder(
        session, user, title=body.title, due_at=due, application_id=body.application_id
    )
    return ReminderOut.model_validate(reminder)


@router.patch("/reminders/{reminder_id}", response_model=ReminderOut)
async def update_reminder(
    reminder_id: uuid.UUID, body: ReminderUpdate, session: SessionDep, user: CurrentUser
) -> ReminderOut:
    reminder = await service.update_reminder(
        session, user, reminder_id, done=body.done, due_at=body.due_at
    )
    return ReminderOut.model_validate(reminder)


@router.delete("/reminders/{reminder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_reminder(reminder_id: uuid.UUID, session: SessionDep, user: CurrentUser) -> None:
    await service.delete_reminder(session, user, reminder_id)


# ------------------------------------------------------------------ dashboard


class NextStepOut(BaseModel):
    title: str
    body: str
    href: str


class DashboardOut(BaseModel):
    applications: dict[str, int]
    interview_trend: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    weak_topics: list[dict[str, Any]]
    streak_days: int
    active_today: bool
    reminders: list[ReminderOut]
    totals: dict[str, int]
    next_step: NextStepOut
    activity: list[str]


@router.get("/dashboard", response_model=DashboardOut)
async def get_dashboard(session: SessionDep, user: CurrentUser) -> DashboardOut:
    data = await dashboard.build(session, user)
    return DashboardOut(
        applications=data.applications,
        interview_trend=data.interview_trend,
        skills=data.skills,
        weak_topics=data.weak_topics,
        streak_days=data.streak_days,
        active_today=data.active_today,
        reminders=[ReminderOut.model_validate(r) for r in data.reminders],
        totals=data.totals,
        next_step=NextStepOut(
            title=data.next_step.title, body=data.next_step.body, href=data.next_step.href
        ),
        activity=data.activity,
    )


# ------------------------------------------------------------------ user reports


class ReportCreate(BaseModel):
    kind: ReportKind
    message: str = Field(min_length=5, max_length=3000)
    target_type: str | None = Field(default=None, max_length=30)
    target_id: str | None = Field(default=None, max_length=64)
    page_url: str | None = Field(default=None, max_length=500)


class UserReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: ReportKind
    target_type: str | None
    target_id: str | None
    message: str
    page_url: str | None
    state: ReportState
    reply: str | None
    created_at: datetime
    handled_at: datetime | None


class AdminUserReportOut(UserReportOut):
    user_email: str | None


class ReportHandle(BaseModel):
    state: ReportState
    reply: str | None = Field(default=None, max_length=3000)


REPORTS_PER_DAY = 20


@router.post(
    "/reports",
    response_model=UserReportOut,
    status_code=status.HTTP_201_CREATED,
    responses={429: {"model": ErrorResponse}},
)
async def create_report(
    body: ReportCreate, session: SessionDep, user: CurrentUser
) -> UserReportOut:
    """Report a wrong question, bad AI feedback, a broken job link, or anything else."""
    from datetime import timedelta

    from app.core.errors import AppError

    recent = await session.scalar(
        select(func.count())
        .select_from(UserReport)
        .where(
            UserReport.user_id == user.id,
            UserReport.created_at >= datetime.now(UTC) - timedelta(days=1),
        )
    )
    if (recent or 0) >= REPORTS_PER_DAY:
        error = AppError(
            "Thanks! You've sent a lot of reports today; we'll review them first.",
            code="rate_limited",
        )
        error.status_code = 429
        raise error
    report = UserReport(user_id=user.id, **body.model_dump())
    session.add(report)
    await session.commit()
    return UserReportOut.model_validate(report)


@router.get("/reports", response_model=list[UserReportOut])
async def my_reports(session: SessionDep, user: CurrentUser) -> list[UserReportOut]:
    rows = await session.scalars(
        select(UserReport)
        .where(UserReport.user_id == user.id)
        .order_by(UserReport.created_at.desc())
        .limit(50)
    )
    return [UserReportOut.model_validate(r) for r in rows]


ReportsReader = Annotated[User, Depends(require_permission(Permission.REPORTS_READ))]
ReportsManager = Annotated[User, Depends(require_permission(Permission.REPORTS_MANAGE))]


@router.get("/admin/reports", response_model=Page[AdminUserReportOut], tags=["admin: reports"])
async def admin_reports(
    session: SessionDep,
    _: ReportsReader,
    state: ReportState | None = ReportState.OPEN,
    kind: ReportKind | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[AdminUserReportOut]:
    stmt = select(UserReport, User.email).outerjoin(User, User.id == UserReport.user_id)
    if state:
        stmt = stmt.where(UserReport.state == state)
    if kind:
        stmt = stmt.where(UserReport.kind == kind)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.execute(
        stmt.order_by(UserReport.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )
    items = [
        AdminUserReportOut(**UserReportOut.model_validate(r).model_dump(), user_email=email)
        for r, email in rows
    ]
    return Page(items=items, total=total, page=page, page_size=page_size)


@router.patch(
    "/admin/reports/{report_id}", response_model=AdminUserReportOut, tags=["admin: reports"]
)
async def handle_report(
    report_id: uuid.UUID,
    body: ReportHandle,
    session: SessionDep,
    actor: ReportsManager,
    meta: RequestMetaDep,
) -> AdminUserReportOut:
    report = await session.get(UserReport, report_id)
    if report is None:
        raise NotFoundError("Report not found")
    before = {"state": report.state.value}
    report.state = body.state
    if body.reply is not None:
        report.reply = body.reply or None
    report.handled_by_id = actor.id
    report.handled_at = datetime.now(UTC)
    await audit.record(
        session,
        actor=actor,
        action="user_report.handled",
        target_type="user_report",
        target_id=report.id,
        before=before,
        after={"state": body.state.value, "replied": bool(body.reply)},
        meta=meta,
    )
    await session.commit()
    owner = await session.get(User, report.user_id) if report.user_id else None
    return AdminUserReportOut(
        **UserReportOut.model_validate(report).model_dump(),
        user_email=owner.email if owner else None,
    )
