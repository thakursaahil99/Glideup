"""Application tracker (Kanban), reminders and the due-reminder email job."""

import uuid
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.email import send_email
from app.core.errors import ConflictError, NotFoundError
from app.db.models import (
    Application,
    ApplicationEvent,
    ApplicationStatus,
    Job,
    Reminder,
    User,
)
from app.db.session import session_factory

logger = structlog.get_logger(__name__)

REMINDER_BATCH = 200


async def list_applications(session: AsyncSession, user: User) -> list[Application]:
    return list(
        await session.scalars(
            select(Application)
            .where(Application.user_id == user.id)
            .order_by(Application.status, Application.position, Application.created_at)
        )
    )


async def get_application(
    session: AsyncSession, user: User, application_id: uuid.UUID
) -> Application:
    application = await session.get(Application, application_id)
    if application is None or application.user_id != user.id:
        raise NotFoundError("Application not found")
    return application


async def _next_position(session: AsyncSession, user: User, status: ApplicationStatus) -> int:
    top = await session.scalar(
        select(func.max(Application.position)).where(
            Application.user_id == user.id, Application.status == status
        )
    )
    return (top if top is not None else -1) + 1


async def create_application(
    session: AsyncSession,
    user: User,
    *,
    job_id: uuid.UUID | None,
    company: str | None,
    title: str | None,
    url: str | None,
    location: str | None,
    status: ApplicationStatus,
    notes: str | None,
) -> Application:
    """Track a board job (details copied from it) or a job found elsewhere."""
    job: Job | None = None
    if job_id is not None:
        job = await session.get(Job, job_id)
        if job is None:
            raise NotFoundError("Job not found")
        existing = await session.scalar(
            select(Application).where(Application.user_id == user.id, Application.job_id == job.id)
        )
        if existing is not None:
            raise ConflictError("You're already tracking this job.", code="already_tracked")
    if job is None and not (company and title):
        raise ConflictError("Give a company and a job title.", code="details_required")
    now = datetime.now(UTC)
    application = Application(
        user_id=user.id,
        job_id=job.id if job else None,
        company=job.company_name if job else (company or ""),
        title=job.title if job else (title or ""),
        url=job.apply_url if job else url,
        location=job.location if job else location,
        status=status,
        position=await _next_position(session, user, status),
        applied_at=now if status != ApplicationStatus.SAVED else None,
        notes=notes,
    )
    application.events = [ApplicationEvent(kind="created", to_status=status.value, created_at=now)]
    session.add(application)
    await session.commit()
    return application


async def update_application(
    session: AsyncSession,
    user: User,
    application_id: uuid.UUID,
    *,
    status: ApplicationStatus | None = None,
    position: int | None = None,
    notes: str | None = None,
    salary: str | None = None,
    note: str | None = None,
) -> Application:
    """Move between columns (logged on the timeline), reorder, edit notes, add a note."""
    application = await get_application(session, user, application_id)
    now = datetime.now(UTC)
    if status is not None and status != application.status:
        application.events.append(
            ApplicationEvent(kind="status", from_status=application.status.value,
                             to_status=status.value, created_at=now)
        )  # fmt: skip
        if application.applied_at is None and status != ApplicationStatus.SAVED:
            application.applied_at = now
        application.status = status
        if position is None:
            position = await _next_position(session, user, status)
    if position is not None:
        # Shift the others in the destination column to make room.
        await session.execute(
            update(Application)
            .where(
                Application.user_id == user.id,
                Application.status == application.status,
                Application.position >= position,
                Application.id != application.id,
            )
            .values(position=Application.position + 1)
        )
        application.position = position
    if notes is not None:
        application.notes = notes or None
    if salary is not None:
        application.salary = salary or None
    if note:
        application.events.append(ApplicationEvent(kind="note", note=note, created_at=now))
    await session.commit()
    await session.refresh(application)
    return application


async def delete_application(session: AsyncSession, user: User, application_id: uuid.UUID) -> None:
    application = await get_application(session, user, application_id)
    await session.delete(application)
    await session.commit()


# ------------------------------------------------------------------ reminders


async def list_reminders(
    session: AsyncSession, user: User, *, include_done: bool = False
) -> list[Reminder]:
    stmt = select(Reminder).where(Reminder.user_id == user.id).order_by(Reminder.due_at)
    if not include_done:
        stmt = stmt.where(Reminder.done.is_(False))
    return list(await session.scalars(stmt))


async def create_reminder(
    session: AsyncSession,
    user: User,
    *,
    title: str,
    due_at: datetime,
    application_id: uuid.UUID | None,
) -> Reminder:
    if application_id is not None:
        await get_application(session, user, application_id)
    reminder = Reminder(user_id=user.id, title=title, due_at=due_at, application_id=application_id)
    session.add(reminder)
    await session.commit()
    return reminder


async def update_reminder(
    session: AsyncSession,
    user: User,
    reminder_id: uuid.UUID,
    *,
    done: bool | None,
    due_at: datetime | None,
) -> Reminder:
    reminder = await session.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise NotFoundError("Reminder not found")
    if done is not None:
        reminder.done = done
    if due_at is not None:
        reminder.due_at = due_at
        reminder.emailed_at = None  # rescheduled: email again when due
    await session.commit()
    return reminder


async def delete_reminder(session: AsyncSession, user: User, reminder_id: uuid.UUID) -> None:
    reminder = await session.get(Reminder, reminder_id)
    if reminder is None or reminder.user_id != user.id:
        raise NotFoundError("Reminder not found")
    await session.delete(reminder)
    await session.commit()


async def send_due_reminders_job() -> int:
    """Email reminders that are due and not yet emailed. Marks each before sending so a
    crash can't email twice; at worst one is skipped (it still shows in the app)."""
    now = datetime.now(UTC)
    sent = 0
    async with session_factory()() as session:
        rows = (
            await session.execute(
                select(Reminder, User.email, User.name)
                .join(User, User.id == Reminder.user_id)
                .where(
                    Reminder.done.is_(False), Reminder.emailed_at.is_(None), Reminder.due_at <= now
                )
                .order_by(Reminder.due_at)
                .limit(REMINDER_BATCH)
            )
        ).all()
        for reminder, _, _ in rows:
            reminder.emailed_at = now
        await session.commit()
    web = get_settings().web_url.rstrip("/")
    for reminder, email, name in rows:
        greeting = f"Hi {name.split(' ')[0]}," if name else "Hi,"
        body = (
            f"{greeting}\n\nReminder: {reminder.title}\n\n"
            f"See your applications: {web}/tracker\n\n— GlideUp"
        )
        if await send_email(email, f"Reminder: {reminder.title}", body):
            sent += 1
    if rows:
        logger.info("reminders_processed", due=len(rows), emailed=sent)
    return sent


def overdue(reminder: Reminder, now: datetime | None = None) -> bool:
    due = reminder.due_at if reminder.due_at.tzinfo else reminder.due_at.replace(tzinfo=UTC)
    return not reminder.done and due < (now or datetime.now(UTC)) - timedelta(seconds=0)
