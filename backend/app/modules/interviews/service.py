"""Interviews: types, creation, history, WebSocket tickets and housekeeping."""

import uuid
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import structlog
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError, UnauthorizedError
from app.db.models import (
    Difficulty,
    Interview,
    InterviewReport,
    InterviewStatus,
    InterviewType,
    Job,
    User,
)
from app.db.session import session_factory
from app.llm.types import CallContext
from app.modules.interviews import planning
from app.modules.interviews.defaults import DEFAULT_TYPES
from app.workers.runtime import dispatch

logger = structlog.get_logger(__name__)

TICKET_TTL = timedelta(seconds=60)
RECENT_QUESTIONS = 20  # avoid repeating questions from the user's last N interviews
PREPARE_STUCK_AFTER = timedelta(minutes=30)
EXPIRE_GRACE = timedelta(minutes=2)


class QuotaExceededError(AppError):
    status_code = 429
    code = "quota_exceeded"


# ------------------------------------------------------------------ types


async def ensure_types(session: AsyncSession) -> None:
    """Insert shipped interview types that are missing. Never overwrites admin edits."""
    existing = set(await session.scalars(select(InterviewType.key)))
    for spec in DEFAULT_TYPES:
        if spec["key"] not in existing:
            try:  # concurrent callers may race; the loser skips the row
                async with session.begin_nested():
                    session.add(InterviewType(**spec))
            except IntegrityError:
                pass


async def list_types(session: AsyncSession, *, enabled_only: bool = True) -> list[InterviewType]:
    await ensure_types(session)
    stmt = select(InterviewType).order_by(InterviewType.sort_order, InterviewType.name)
    if enabled_only:
        stmt = stmt.where(InterviewType.enabled.is_(True))
    return list(await session.scalars(stmt))


# ------------------------------------------------------------------ interviews


async def get_owned(session: AsyncSession, user: User, interview_id: uuid.UUID) -> Interview:
    interview = await session.get(Interview, interview_id)
    if interview is None or interview.user_id != user.id:
        raise NotFoundError("Interview not found")
    return interview


async def list_for_user(
    session: AsyncSession, user: User, limit: int = 50
) -> list[tuple[Interview, InterviewReport | None]]:
    rows = await session.execute(
        select(Interview, InterviewReport)
        .outerjoin(InterviewReport, InterviewReport.interview_id == Interview.id)
        .where(Interview.user_id == user.id)
        .order_by(Interview.created_at.desc())
        .limit(limit)
    )
    return [(i, r) for i, r in rows]


async def _recent_prompts(session: AsyncSession, user: User) -> set[str]:
    plans: Iterable[list[dict[str, Any]]] = await session.scalars(
        select(Interview.plan)
        .where(Interview.user_id == user.id)
        .order_by(Interview.created_at.desc())
        .limit(RECENT_QUESTIONS)
    )
    return {q["prompt"] for plan in plans for q in plan or []}


async def create(
    session: AsyncSession,
    user: User,
    *,
    type_key: str,
    difficulty: Difficulty | None,
    job_id: uuid.UUID | None,
) -> Interview:
    await ensure_types(session)
    type_ = await session.get(InterviewType, type_key)
    if type_ is None or not type_.enabled:
        raise NotFoundError("That interview type isn't available.")

    limit = get_settings().interviews_daily_limit
    since = datetime.now(UTC) - timedelta(days=1)
    started_today = await session.scalar(
        select(func.count())
        .select_from(Interview)
        .where(Interview.user_id == user.id, Interview.created_at >= since)
    )
    if (started_today or 0) >= limit:
        raise QuotaExceededError(
            f"You've started {limit} interviews in the last 24 hours. Take a break and "
            "come back tomorrow."
        )

    job: Job | None = None
    if job_id is not None:
        job = await session.get(Job, job_id)
        if job is None or job.is_hidden:
            raise NotFoundError("Job not found")
    if type_.key == "job_specific" and job is None:
        raise AppError("Pick a job for a job-specific interview.", code="job_required")

    from app.modules.resumes import service as resumes

    resume = await resumes.get_active(session, user.id)
    level = difficulty or type_.difficulty
    interview = Interview(
        user_id=user.id,
        type_key=type_.key,
        job_id=job.id if job else None,
        resume_id=resume.id if resume else None,
        status=InterviewStatus.READY,
        difficulty=level,
        duration_minutes=type_.duration_minutes,
        max_followups=type_.max_followups,
        rubric=list(type_.rubric),
        plan=[],
        job_title=job.title if job else None,
        company_name=job.company_name if job else None,
    )
    if type_.key == "job_specific":
        interview.status = InterviewStatus.PREPARING
    else:
        interview.plan = planning.pick_from_bank(
            type_.key, level, type_.question_count, avoid=await _recent_prompts(session, user)
        )
        if not interview.plan:
            raise ConflictError("No questions are available for this interview type yet.")
    session.add(interview)
    await session.commit()
    if interview.status == InterviewStatus.PREPARING:
        from app.modules.interviews import tasks

        dispatch(tasks.prepare_interview, prepare_interview_job, str(interview.id))
    return interview


async def prepare_interview_job(interview_id: str) -> None:
    """Write the questions for a job-specific interview (background job)."""
    from app.modules.matching.service import candidate_text, load_candidate

    async with session_factory()() as session:
        interview = await session.get(Interview, uuid.UUID(interview_id))
        if interview is None or interview.status != InterviewStatus.PREPARING:
            return
        job = await session.get(Job, interview.job_id) if interview.job_id else None
        type_ = await session.get(InterviewType, interview.type_key)
        if job is None or type_ is None:
            interview.status = InterviewStatus.FAILED
            interview.error = "The job for this interview is no longer available."
            await session.commit()
            return
        candidate = await load_candidate(session, interview.user_id)
        await session.commit()  # nothing held open during the LLM call
        plan, source = await planning.job_plan(
            job,
            candidate_text=candidate_text(candidate) if candidate else "",
            have=set(candidate.have) if candidate else set(),
            count=type_.question_count,
            difficulty=interview.difficulty,
            ctx=CallContext(user_id=interview.user_id),
        )
        interview.plan = plan
        interview.status = InterviewStatus.READY
        await session.commit()
        logger.info("interview_prepared", interview_id=interview_id, source=source)


# ------------------------------------------------------------------ WebSocket tickets


def _ticket_key() -> str:
    return get_settings().jwt_secret.get_secret_value()


async def issue_ticket(session: AsyncSession, interview: Interview) -> str:
    """A single-use, 60-second token for opening this interview's WebSocket. Browsers
    can't send auth headers on WebSockets, and our access tokens never reach browser JS
    (they live in the BFF), so the BFF fetches this ticket for the page instead."""
    settings = get_settings()
    jti = uuid.uuid4()
    now = datetime.now(UTC)
    interview.ws_ticket_jti = jti
    await session.commit()
    return jwt.encode(
        {
            "sub": str(interview.user_id),
            "iid": str(interview.id),
            "typ": "ws",
            "jti": str(jti),
            "iat": int(now.timestamp()),
            "exp": int((now + TICKET_TTL).timestamp()),
            "iss": settings.jwt_issuer,
            "aud": settings.jwt_audience,
        },
        _ticket_key(),
        algorithm=settings.jwt_algorithm,
    )


async def redeem_ticket(session: AsyncSession, token: str, interview_id: uuid.UUID) -> User:
    """Validate a ticket for this interview and burn it (atomically, so it works once)."""
    settings = get_settings()
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            _ticket_key(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "iid", "typ", "jti", "exp"]},
        )
        jti = uuid.UUID(payload["jti"])
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise UnauthorizedError("Invalid or expired ticket", code="invalid_ticket") from exc
    if payload["typ"] != "ws" or payload["iid"] != str(interview_id):
        raise UnauthorizedError("Invalid ticket", code="invalid_ticket")
    burned = await session.execute(
        update(Interview)
        .where(
            Interview.id == interview_id,
            Interview.user_id == user_id,
            Interview.ws_ticket_jti == jti,
        )
        .values(ws_ticket_jti=None)
        .returning(Interview.id)
    )
    if burned.first() is None:
        raise UnauthorizedError("This ticket was already used", code="invalid_ticket")
    user = await session.get(User, user_id)
    await session.commit()
    if user is None or not user.is_active:
        raise UnauthorizedError("Account unavailable", code="invalid_ticket")
    return user


# ------------------------------------------------------------------ housekeeping


async def expire_due_job() -> int:
    """Finish interviews whose time ran out while nobody was connected, and fail
    preparations that got stuck. Runs on a schedule."""
    from app.modules.interviews import engine

    now = datetime.now(UTC)
    finished = 0
    async with session_factory()() as session:
        overdue = list(
            await session.scalars(
                select(Interview.id).where(
                    Interview.status == InterviewStatus.IN_PROGRESS,
                    Interview.ends_at < now - EXPIRE_GRACE,
                )
            )
        )
        await session.execute(
            update(Interview)
            .where(
                Interview.status == InterviewStatus.PREPARING,
                Interview.created_at < now - PREPARE_STUCK_AFTER,
            )
            .values(status=InterviewStatus.FAILED, error="Preparing the questions took too long.")
        )
        await session.commit()

    async def _ignore(_: dict[str, Any]) -> None:
        return None

    for interview_id in overdue:
        async with engine.lock_for(interview_id), session_factory()() as session:
            interview = await session.get(Interview, interview_id)
            if interview is not None and interview.status == InterviewStatus.IN_PROGRESS:
                await engine.finish(session, interview, "time_up", _ignore)
                finished += 1
    return finished
