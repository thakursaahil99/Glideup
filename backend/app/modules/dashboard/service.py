"""The user dashboard: one aggregate read across the whole journey."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.types import Date

from app.db.models import (
    Application,
    ApplicationStatus,
    FrameworkAttempt,
    Interview,
    InterviewReport,
    InterviewType,
    Reminder,
    ReportStatus,
    Resume,
    SkillScore,
    Submission,
    User,
    Verdict,
)

WEAK_CRITERION = 2.5  # average rubric score (1-5) at or below this is a weak topic
WEAK_SECTION = 50  # framework test section score (0-100) below this is a weak topic
TREND_POINTS = 10
STREAK_LOOKBACK_DAYS = 120


@dataclass
class NextStep:
    title: str
    body: str
    href: str


@dataclass
class Dashboard:
    applications: dict[str, int]
    interview_trend: list[dict[str, Any]]
    skills: list[dict[str, Any]]
    weak_topics: list[dict[str, Any]]
    streak_days: int
    active_today: bool
    reminders: list[Reminder]
    totals: dict[str, int]
    next_step: NextStep
    activity: list[str] = field(default_factory=list)  # ISO dates with practice, newest first


def streak(days: set[date], today: date) -> tuple[int, bool]:
    """Consecutive days with practice ending today (or yesterday, so a streak isn't lost
    before the user has had a chance to practise today)."""
    active_today = today in days
    cursor = today if active_today else today - timedelta(days=1)
    count = 0
    while cursor in days:
        count += 1
        cursor -= timedelta(days=1)
    return count, active_today


def next_step(
    *,
    has_resume: bool,
    applications: int,
    interviews: int,
    tests: int,
    reminders_due: int,
    weakest: str | None,
) -> NextStep:
    if not has_resume:
        return NextStep(
            "Upload your resume",
            "We'll match you with real jobs and tailor practice to you.",
            "/onboarding",
        )
    if reminders_due:
        plural = "s are" if reminders_due > 1 else " is"
        return NextStep(
            "Follow up on your applications", f"{reminders_due} reminder{plural} due.", "/tracker"
        )
    if applications == 0:
        return NextStep(
            "Pick jobs to go after",
            "Save or track a few jobs that fit you well.",
            "/jobs/recommended",
        )
    if interviews == 0:
        return NextStep(
            "Do a mock interview",
            "Practise before the real one; you'll get a scored report.",
            "/interviews",
        )
    if tests == 0:
        return NextStep(
            "Take a skill test", "Turn your skills into verified levels on your profile.", "/tests"
        )
    if weakest:
        return NextStep(
            f"Work on {weakest}",
            "It's your weakest area in recent interviews and tests.",
            "/interviews",
        )
    return NextStep(
        "Keep the streak going", "Solve one problem or do a short interview today.", "/tests"
    )


async def build(session: AsyncSession, user: User) -> Dashboard:
    now = datetime.now(UTC)
    apps = dict(
        (
            await session.execute(
                select(Application.status, func.count())
                .where(Application.user_id == user.id)
                .group_by(Application.status)
            )
        ).all()
    )
    applications = {s.value: int(apps.get(s, 0)) for s in ApplicationStatus}

    reports = (
        await session.execute(
            select(InterviewReport, Interview.type_key, Interview.ended_at, Interview.rubric)
            .join(Interview, Interview.id == InterviewReport.interview_id)
            .where(Interview.user_id == user.id, InterviewReport.status == ReportStatus.DONE)
            .order_by(Interview.ended_at.desc())
            .limit(TREND_POINTS)
        )
    ).all()
    type_names = dict((await session.execute(select(InterviewType.key, InterviewType.name))).all())
    trend = [
        {
            "date": (ended or report.created_at).isoformat(),
            "score": report.overall_score,
            "type": type_names.get(type_key, type_key),
        }
        for report, type_key, ended, _ in reversed(reports)
    ]

    weak: dict[str, list[float]] = defaultdict(list)
    for report, _, _, _ in reports[:5]:
        for criterion in (report.result or {}).get("criteria", []):
            if criterion.get("score") is not None:
                weak[criterion["name"]].append(criterion["score"])
    weak_topics: list[dict[str, Any]] = [
        {"topic": name, "source": "interviews", "score": round(sum(v) / len(v) * 20)}
        for name, v in weak.items()
        if sum(v) / len(v) <= WEAK_CRITERION
    ]
    attempts = list(
        await session.scalars(
            select(FrameworkAttempt)
            .where(FrameworkAttempt.user_id == user.id, FrameworkAttempt.score.is_not(None))
            .order_by(FrameworkAttempt.graded_at.desc())
            .limit(5)
        )
    )
    labels = {
        "mcq": "fundamentals",
        "review": "code review",
        "viva": "explaining concepts",
        "project": "building",
    }
    for attempt in attempts:
        for section, score in (attempt.sections or {}).items():
            if score < WEAK_SECTION:
                topic = f"{attempt.framework_key.title()} {labels.get(section, section)}"
                weak_topics.append({"topic": topic, "source": "tests", "score": score})
    weak_topics.sort(key=lambda t: int(t["score"]))
    weak_topics = weak_topics[:6]

    skills = [
        {"skill": s.skill, "kind": s.kind, "score": s.score, "level": s.level}
        for s in await session.scalars(
            select(SkillScore)
            .where(SkillScore.user_id == user.id)
            .order_by(SkillScore.score.desc())
            .limit(8)
        )
    ]

    since = now - timedelta(days=STREAK_LOOKBACK_DAYS)
    day_sets: set[date] = set()
    activity_sources = (
        (Submission.user_id, Submission.created_at),
        (Interview.user_id, Interview.started_at),
        (FrameworkAttempt.user_id, FrameworkAttempt.created_at),
    )
    for owner, column in activity_sources:
        rows = await session.scalars(
            select(cast(column, Date)).where(owner == user.id, column >= since).distinct()
        )
        day_sets |= {d if isinstance(d, date) else date.fromisoformat(str(d)) for d in rows if d}
    streak_days, active_today = streak(day_sets, now.date())

    reminders = list(
        await session.scalars(
            select(Reminder)
            .where(Reminder.user_id == user.id, Reminder.done.is_(False))
            .order_by(Reminder.due_at)
            .limit(5)
        )
    )
    due = sum(
        1
        for r in reminders
        if (r.due_at if r.due_at.tzinfo else r.due_at.replace(tzinfo=UTC)) <= now
    )
    solved = await session.scalar(
        select(func.count(func.distinct(Submission.question_id))).where(
            Submission.user_id == user.id, Submission.verdict == Verdict.ACCEPTED
        )
    )
    has_resume = bool(
        await session.scalar(select(Resume.id).where(Resume.user_id == user.id).limit(1))
    )
    totals = {
        "applications": sum(applications.values()),
        "interviews": len(reports),
        "problems_solved": int(solved or 0),
        "tests": len(attempts),
    }
    return Dashboard(
        applications=applications,
        interview_trend=trend,
        skills=skills,
        weak_topics=weak_topics,
        streak_days=streak_days,
        active_today=active_today,
        reminders=reminders,
        totals=totals,
        next_step=next_step(
            has_resume=has_resume,
            applications=totals["applications"],
            interviews=totals["interviews"],
            tests=totals["tests"],
            reminders_due=due,
            weakest=weak_topics[0]["topic"] if weak_topics else None,
        ),
        activity=sorted((d.isoformat() for d in day_sets), reverse=True)[:60],
    )
