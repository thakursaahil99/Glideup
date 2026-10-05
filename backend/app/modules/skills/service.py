"""Framework tests, skill scores and badges."""

import hashlib
import random
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.models import (
    AttemptStatus,
    Difficulty,
    Framework,
    FrameworkAttempt,
    Interview,
    InterviewReport,
    Question,
    QuestionStatus,
    ReportStatus,
    SkillScore,
    Submission,
    User,
    UserBadge,
    Verdict,
)
from app.db.session import session_factory
from app.llm.types import AllProvidersFailedError
from app.modules.skills import grading
from app.modules.skills.content import FRAMEWORK_TYPES, public_content, validate_content
from app.modules.skills.seed_content import FRAMEWORKS, QUESTIONS
from app.workers.runtime import dispatch

logger = structlog.get_logger(__name__)

GRACE = timedelta(minutes=2)  # late answers are still saved right after the timer ends
DSA_POINTS = {Difficulty.EASY: 10, Difficulty.MEDIUM: 20, Difficulty.HARD: 35}


# ------------------------------------------------------------------ seed


def shuffled_mcq(slug: str, content: dict[str, Any]) -> dict[str, Any]:
    """Rotate options by a stable per-question amount so the right answer isn't always in
    the same position (the seed data lists it second)."""
    options = list(content["options"])
    shift = int(hashlib.sha256(slug.encode()).hexdigest(), 16) % len(options)
    rotated = options[shift:] + options[:shift]
    return {**content, "options": rotated, "answer": (content["answer"] - shift) % len(options)}


async def seed_frameworks(session: AsyncSession) -> int:
    """Insert shipped frameworks and their questions that are missing. Never overwrites."""
    for spec in FRAMEWORKS:
        if await session.get(Framework, spec["key"]) is None:
            try:
                async with session.begin_nested():
                    session.add(Framework(**spec))
            except IntegrityError:
                pass
    existing = set(await session.scalars(select(Question.slug)))
    created = 0
    for spec in QUESTIONS:
        if spec["slug"] in existing:
            continue
        session.add(
            Question(
                slug=spec["slug"],
                title=spec["title"],
                type=spec["type"],
                framework_key=spec["framework"],
                difficulty=Difficulty(spec["difficulty"]),
                topics=[spec["framework"], spec["type"]],
                statement=spec["statement"],
                content=validate_content(
                    spec["type"],
                    shuffled_mcq(spec["slug"], spec["content"])
                    if spec["type"] == "mcq"
                    else spec["content"],
                ),
                status=QuestionStatus.PUBLISHED,
                source="seed",
                validation={"ok": True, "note": "Framework questions are validated by schema."},
            )
        )
        created += 1
    await session.flush()
    return created


# ------------------------------------------------------------------ frameworks


async def list_frameworks(
    session: AsyncSession, user: User
) -> list[tuple[Framework, int, int | None]]:
    """(framework, available questions, the user's best score)."""
    await seed_frameworks(session)
    await session.commit()
    frameworks = list(
        await session.scalars(
            select(Framework).where(Framework.enabled.is_(True)).order_by(Framework.name)
        )
    )
    counts = dict(
        (
            await session.execute(
                select(Question.framework_key, func.count())
                .where(
                    Question.status == QuestionStatus.PUBLISHED, Question.framework_key.is_not(None)
                )
                .group_by(Question.framework_key)
            )
        ).all()
    )
    best = {
        s.skill: s.score
        for s in await session.scalars(
            select(SkillScore).where(SkillScore.user_id == user.id, SkillScore.kind == "framework")
        )
    }
    return [(f, counts.get(f.key, 0), best.get(f.key)) for f in frameworks]


async def start_attempt(session: AsyncSession, user: User, framework_key: str) -> FrameworkAttempt:
    framework = await session.get(Framework, framework_key)
    if framework is None or not framework.enabled:
        raise NotFoundError("Framework not found")
    open_attempt = await session.scalar(
        select(FrameworkAttempt).where(
            FrameworkAttempt.user_id == user.id,
            FrameworkAttempt.framework_key == framework_key,
            FrameworkAttempt.status == AttemptStatus.IN_PROGRESS,
            FrameworkAttempt.ends_at > datetime.now(UTC),
        )
    )
    if open_attempt is not None:
        return open_attempt  # resume instead of starting a second one
    seen = {
        qid
        for ids in await session.scalars(
            select(FrameworkAttempt.question_ids).where(
                FrameworkAttempt.user_id == user.id, FrameworkAttempt.framework_key == framework_key
            )
        )
        for qid in ids
    }
    rng = random.Random()  # noqa: S311 - variety, not security
    chosen: list[str] = []
    for question_type in FRAMEWORK_TYPES:
        wanted = int((framework.composition or {}).get(question_type, 0))
        pool = list(
            await session.scalars(
                select(Question.id).where(
                    Question.framework_key == framework_key,
                    Question.type == question_type,
                    Question.status == QuestionStatus.PUBLISHED,
                )
            )
        )
        rng.shuffle(pool)
        pool.sort(key=lambda qid: str(qid) in seen)  # unseen first, stable within groups
        chosen += [str(qid) for qid in pool[:wanted]]
    if not chosen:
        raise ConflictError("This test has no questions yet.", code="no_questions")
    attempt = FrameworkAttempt(
        user_id=user.id,
        framework_key=framework_key,
        question_ids=chosen,
        answers={},
        ends_at=datetime.now(UTC) + timedelta(minutes=framework.duration_minutes),
    )
    session.add(attempt)
    await session.commit()
    return attempt


async def get_attempt(session: AsyncSession, user: User, attempt_id: uuid.UUID) -> FrameworkAttempt:
    attempt = await session.get(FrameworkAttempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise NotFoundError("Test not found")
    return attempt


async def attempt_questions(session: AsyncSession, attempt: FrameworkAttempt) -> list[Question]:
    ids = [uuid.UUID(q) for q in attempt.question_ids]
    by_id = {q.id: q for q in await session.scalars(select(Question).where(Question.id.in_(ids)))}
    return [by_id[i] for i in ids if i in by_id]


def question_view(question: Question, *, reveal: bool) -> dict[str, Any]:
    content = question.content or {}
    view: dict[str, Any] = {
        "id": str(question.id),
        "type": question.type,
        "title": question.title,
        "statement": question.statement,
        "content": public_content(question.type, content),
    }
    if reveal and question.type == "mcq":
        view["content"] |= {
            "answer": content.get("answer"),
            "explanation": content.get("explanation"),
        }
    return view


def _aware(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


async def save_answers(
    session: AsyncSession, user: User, attempt_id: uuid.UUID, answers: dict[str, Any]
) -> FrameworkAttempt:
    attempt = await get_attempt(session, user, attempt_id)
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise ConflictError("This test has already been submitted.", code="attempt_closed")
    if datetime.now(UTC) > _aware(attempt.ends_at) + GRACE:
        raise ConflictError("Time is up for this test.", code="time_up")
    allowed = set(attempt.question_ids)
    unknown = set(answers) - allowed
    if unknown:
        raise AppError("Answers for questions not in this test.", code="unknown_question")
    merged = dict(attempt.answers or {})
    for key, value in answers.items():
        if isinstance(value, str):
            value = value[: grading.MAX_ANSWER]
        merged[key] = value
    attempt.answers = merged
    await session.commit()
    return attempt


async def submit_attempt(
    session: AsyncSession, user: User, attempt_id: uuid.UUID
) -> FrameworkAttempt:
    attempt = await get_attempt(session, user, attempt_id)
    if attempt.status not in (AttemptStatus.IN_PROGRESS, AttemptStatus.FAILED):
        return attempt  # already submitted: idempotent
    attempt.status = AttemptStatus.GRADING
    attempt.submitted_at = attempt.submitted_at or datetime.now(UTC)
    attempt.error = None
    await session.commit()
    from app.modules.skills import tasks

    dispatch(tasks.grade_attempt, grade_attempt_job, str(attempt.id))
    return attempt


async def grade_attempt_job(attempt_id: str) -> None:
    async with session_factory()() as session:
        attempt = await session.get(FrameworkAttempt, uuid.UUID(attempt_id))
        if attempt is None or attempt.status != AttemptStatus.GRADING:
            return
        framework = await session.get(Framework, attempt.framework_key)
        questions = await attempt_questions(session, attempt)
        answers = dict(attempt.answers or {})
        await session.commit()  # nothing held open during LLM calls
        results: dict[str, Any] = {}
        sections: dict[str, list[float]] = {}
        try:
            for question in questions:
                answer = answers.get(str(question.id))
                content = question.content or {}
                if question.type == "mcq":
                    graded = grading.grade_mcq(content, answer)
                else:
                    graded = await grading.grade_open(
                        framework=framework.name if framework else attempt.framework_key,
                        question_type=question.type,
                        statement=question.statement,
                        content=content,
                        answer=answer if isinstance(answer, str) else "",
                        user_id=attempt.user_id,
                    )
                results[str(question.id)] = {
                    "score": graded.score,
                    "feedback": graded.feedback,
                    "items": graded.items,
                }
                sections.setdefault(question.type, []).append(graded.score)
        except AllProvidersFailedError:
            attempt.status = AttemptStatus.FAILED
            attempt.error = "Our AI grader is unavailable right now. Try again in a few minutes."
            await session.commit()
            return
        overall, averages = grading.combine(sections)
        attempt.results = results
        attempt.sections = averages
        attempt.score = overall
        attempt.level = grading.level_for(overall)
        attempt.status = AttemptStatus.GRADED
        attempt.graded_at = datetime.now(UTC)
        await record_skill(
            session,
            attempt.user_id,
            attempt.framework_key,
            "framework",
            overall,
            {"attempt": str(attempt.id)},
        )
        await award_badges(session, attempt.user_id)
        await session.commit()
        logger.info("framework_attempt_graded", attempt_id=attempt_id, score=overall)


# ------------------------------------------------------------------ skill scores


async def record_skill(
    session: AsyncSession,
    user_id: uuid.UUID,
    skill: str,
    kind: str,
    score: int,
    evidence: dict[str, Any],
) -> SkillScore:
    """Keep the best score per skill (a bad day doesn't erase a proven level)."""
    row = await session.get(SkillScore, (user_id, skill))
    if row is None:
        row = SkillScore(
            user_id=user_id,
            skill=skill,
            kind=kind,
            score=score,
            level=grading.level_for(score),
            evidence=evidence,
        )
        session.add(row)
    elif score > row.score:
        row.score, row.level, row.evidence = score, grading.level_for(score), evidence
    await session.flush()
    return row


async def update_language_skill(session: AsyncSession, user_id: uuid.UUID, language: str) -> None:
    """Language skill from solved problems: easy 10, medium 20, hard 35 points, capped at 100."""
    rows = await session.execute(
        select(Question.id, Question.difficulty)
        .join(Submission, Submission.question_id == Question.id)
        .where(
            Submission.user_id == user_id,
            Submission.language_key == language,
            Submission.verdict == Verdict.ACCEPTED,
        )
        .distinct()
    )
    solved = list(rows)
    score = min(100, sum(DSA_POINTS[d] for _, d in solved))
    if score:
        await record_skill(session, user_id, language, "language", score, {"solved": len(solved)})


# ------------------------------------------------------------------ badges


@dataclass(frozen=True)
class BadgeDef:
    key: str
    name: str
    description: str


def badge_catalog(frameworks: list[str]) -> dict[str, BadgeDef]:
    defs = [
        BadgeDef("first-accepted", "First green", "Solved your first coding problem."),
        BadgeDef("problem-solver", "Problem solver", "Solved 5 different coding problems."),
        BadgeDef("polyglot", "Polyglot", "Solved problems in 3 different languages."),
        BadgeDef("interview-ready", "Interview ready", "Scored 70+ in a mock interview."),
    ]
    for fw in frameworks:
        defs += [
            BadgeDef(
                f"{fw}-practitioner", f"{fw.title()} practitioner", f"Scored 60+ in the {fw} test."
            ),
            BadgeDef(f"{fw}-expert", f"{fw.title()} expert", f"Scored 85+ in the {fw} test."),
        ]
    return {d.key: d for d in defs}


async def award_badges(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Award every badge the user now qualifies for. Idempotent; returns the new ones."""
    have = set(await session.scalars(select(UserBadge.badge).where(UserBadge.user_id == user_id)))
    accepted = select(Submission).where(
        Submission.user_id == user_id, Submission.verdict == Verdict.ACCEPTED
    )
    solved = (
        await session.scalar(select(func.count(distinct(accepted.subquery().c.question_id)))) or 0
    )
    languages = (
        await session.scalar(select(func.count(distinct(accepted.subquery().c.language_key)))) or 0
    )
    best_interview = await session.scalar(
        select(func.max(InterviewReport.overall_score))
        .join(Interview, Interview.id == InterviewReport.interview_id)
        .where(Interview.user_id == user_id, InterviewReport.status == ReportStatus.DONE)
    )
    earned = []
    if solved >= 1:
        earned.append("first-accepted")
    if solved >= 5:
        earned.append("problem-solver")
    if languages >= 3:
        earned.append("polyglot")
    if (best_interview or 0) >= 70:
        earned.append("interview-ready")
    for score in await session.scalars(
        select(SkillScore).where(SkillScore.user_id == user_id, SkillScore.kind == "framework")
    ):
        if score.score >= 60:
            earned.append(f"{score.skill}-practitioner")
        if score.score >= 85:
            earned.append(f"{score.skill}-expert")
    new = [b for b in earned if b not in have]
    now = datetime.now(UTC)
    for badge in new:
        session.add(UserBadge(user_id=user_id, badge=badge, awarded_at=now, context={}))
    await session.flush()
    return new


async def skills_overview(
    session: AsyncSession, user: User
) -> tuple[list[SkillScore], list[tuple[UserBadge, BadgeDef]]]:
    scores = list(
        await session.scalars(
            select(SkillScore)
            .where(SkillScore.user_id == user.id)
            .order_by(SkillScore.score.desc())
        )
    )
    frameworks = list(await session.scalars(select(Framework.key)))
    catalog = badge_catalog(frameworks)
    badges = [
        (b, catalog[b.badge])
        for b in await session.scalars(
            select(UserBadge).where(UserBadge.user_id == user.id).order_by(UserBadge.awarded_at)
        )
        if b.badge in catalog
    ]
    return scores, badges
