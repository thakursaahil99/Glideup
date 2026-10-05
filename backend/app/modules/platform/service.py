"""Platform controls: feature flags, LLM settings and usage, system health, announcements."""

import asyncio
import hashlib
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import case, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.core.redis import RedisError, get_redis
from app.db.models import (
    Announcement,
    AttemptStatus,
    FeatureFlag,
    FrameworkAttempt,
    GenerationStatus,
    IngestionRun,
    InterviewReport,
    JobSource,
    LLMUsage,
    QuestionGeneration,
    ReportStatus,
    Resume,
    ResumeStatus,
    RunStatus,
    SiteSetting,
)
from app.llm import runtime
from app.llm.factory import get_gateway
from app.llm.routing import DEFAULT_ROUTES, Route, routes_for

logger = structlog.get_logger(__name__)

# ------------------------------------------------------------------ feature flags

DEFAULT_FLAGS: dict[str, tuple[str, bool]] = {
    "voice_mode": ("Voice answers and read-aloud in mock interviews.", True),
    "framework_tests": ("Framework tests (React, FastAPI, ...).", True),
    "ai_skill_gap": ("The AI skill-gap coach on job pages.", True),
    "job_specific_interviews": ("Interviews written from a job description.", True),
    "ai_question_generation": ("AI question generation for admins.", True),
}
FLAGS_TTL_S = 30.0


@dataclass(frozen=True)
class FlagState:
    """A plain snapshot (ORM rows must not outlive their session in the cache)."""

    enabled: bool
    rollout_percent: int
    allow_user_ids: tuple[str, ...]


_flags: dict[str, FlagState] = {}
_flags_loaded = -FLAGS_TTL_S


class FeatureDisabledError(AppError):
    status_code = 403
    code = "feature_disabled"


async def ensure_flags(session: AsyncSession) -> None:
    existing = set(await session.scalars(select(FeatureFlag.key)))
    for key, (description, enabled) in DEFAULT_FLAGS.items():
        if key not in existing:
            session.add(
                FeatureFlag(
                    key=key,
                    description=description,
                    enabled=enabled,
                    rollout_percent=100,
                    allow_user_ids=[],
                )
            )
    await session.flush()


def invalidate_flags() -> None:
    global _flags_loaded
    _flags_loaded = -FLAGS_TTL_S


async def _load_flags(session: AsyncSession) -> dict[str, FlagState]:
    global _flags, _flags_loaded
    if time.monotonic() - _flags_loaded >= FLAGS_TTL_S:
        rows = list(await session.scalars(select(FeatureFlag)))
        _flags = {
            f.key: FlagState(f.enabled, f.rollout_percent, tuple(f.allow_user_ids or []))
            for f in rows
        }
        _flags_loaded = time.monotonic()
    return _flags


def flag_on(
    flag: FlagState | FeatureFlag | None, key: str, user_id: uuid.UUID | str | None
) -> bool:
    if flag is None:  # not configured yet: the shipped default
        return DEFAULT_FLAGS.get(key, ("", False))[1]
    if user_id is not None and str(user_id) in (flag.allow_user_ids or []):
        return True
    if not flag.enabled:
        return False
    if flag.rollout_percent >= 100 or user_id is None:
        return flag.rollout_percent >= 100
    bucket = int(hashlib.sha256(f"{key}:{user_id}".encode()).hexdigest()[:8], 16) % 100
    return bucket < flag.rollout_percent


async def is_enabled(session: AsyncSession, key: str, user_id: uuid.UUID | None) -> bool:
    flags = await _load_flags(session)
    return flag_on(flags.get(key), key, user_id)


async def require_flag(session: AsyncSession, key: str, user_id: uuid.UUID | None) -> None:
    if not await is_enabled(session, key, user_id):
        raise FeatureDisabledError("This feature is currently turned off.", details={"flag": key})


async def flags_for(session: AsyncSession, user_id: uuid.UUID) -> dict[str, bool]:
    flags = await _load_flags(session)
    return {key: flag_on(flags.get(key), key, user_id) for key in DEFAULT_FLAGS}


# ------------------------------------------------------------------ LLM settings & usage


def known_providers() -> list[str]:
    return sorted(get_gateway().providers)


def validate_settings(values: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    providers = set(known_providers()) | {"ollama", "github", "openrouter", "mock"}
    for key, value in values.items():
        if key not in runtime.DEFAULTS:
            raise AppError(f"Unknown setting '{key}'", code="invalid_setting")
        if key == "llm.routes":
            if not isinstance(value, dict):
                raise AppError(
                    "llm.routes must map task -> list of provider:model", code="invalid_setting"
                )
            routes: dict[str, list[str]] = {}
            for task, specs in value.items():
                if task not in DEFAULT_ROUTES:
                    raise AppError(f"Unknown task '{task}'", code="invalid_setting")
                if not isinstance(specs, list) or not specs:
                    continue  # empty = back to the default
                parsed = []
                for spec in specs:
                    try:
                        route = Route.parse(str(spec))
                    except ValueError as exc:
                        raise AppError(str(exc), code="invalid_setting") from exc
                    if route.provider not in providers:
                        raise AppError(
                            f"Unknown provider '{route.provider}'", code="invalid_setting"
                        )
                    parsed.append(str(route))
                if task == "embedding" and len(parsed) > 1:
                    raise AppError("Embeddings must use exactly one model.", code="invalid_setting")
                routes[task] = parsed
            clean[key] = routes
        elif key == "llm.cache_enabled":
            clean[key] = bool(value)
        elif key == "llm.cache_ttl_hours":
            hours = int(value)
            if not 1 <= hours <= 24 * 30:
                raise AppError("Cache TTL must be 1-720 hours.", code="invalid_setting")
            clean[key] = hours
        elif key == "llm.user_daily_token_budget":
            budget = int(value)
            if budget < 0:
                raise AppError("Budget can't be negative.", code="invalid_setting")
            clean[key] = budget
    return clean


async def current_settings(session: AsyncSession) -> dict[str, Any]:
    rows = await session.scalars(
        select(SiteSetting).where(SiteSetting.key.in_(list(runtime.DEFAULTS)))
    )
    return {**runtime.DEFAULTS, **{r.key: r.value for r in rows}}


async def save_settings(session: AsyncSession, values: dict[str, Any]) -> dict[str, Any]:
    for key, value in values.items():
        row = await session.get(SiteSetting, key)
        if row is None:
            session.add(SiteSetting(key=key, value=value))
        else:
            row.value = value
    await session.flush()
    merged = await current_settings(session)
    runtime.apply(merged)
    return merged


def effective_routes() -> dict[str, list[str]]:
    settings = get_settings()
    return {task: [str(r) for r in routes_for(task, settings)] for task in DEFAULT_ROUTES}


async def usage_report(session: AsyncSession, days: int) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await session.execute(
        select(
            LLMUsage.provider,
            LLMUsage.model,
            LLMUsage.task,
            func.count(),
            func.sum(case((LLMUsage.success.is_(False), 1), else_=0)),
            func.sum(case((LLMUsage.cached.is_(True), 1), else_=0)),
            func.sum(LLMUsage.prompt_tokens),
            func.sum(LLMUsage.completion_tokens),
            func.sum(LLMUsage.estimated_cost_usd),
            func.avg(LLMUsage.latency_ms),
        )
        .where(LLMUsage.created_at >= since)
        .group_by(LLMUsage.provider, LLMUsage.model, LLMUsage.task)
        .order_by(func.count().desc())
    )
    return [
        {
            "provider": provider,
            "model": model,
            "task": task,
            "calls": calls,
            "errors": int(errors or 0),
            "cached": int(cached or 0),
            "error_rate": round((errors or 0) / calls, 3) if calls else 0,
            "prompt_tokens": int(pt or 0),
            "completion_tokens": int(ct or 0),
            "cost_usd": float(cost or 0),
            "avg_latency_ms": round(float(avg or 0)),
        }
        for provider, model, task, calls, errors, cached, pt, ct, cost, avg in rows
    ]


# ------------------------------------------------------------------ system health


@dataclass
class Check:
    name: str
    status: str  # ok | degraded | down | off
    detail: str = ""
    latency_ms: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def _timed(name: str, probe: Any) -> Check:
    started = time.perf_counter()
    try:
        result: Check = await asyncio.wait_for(probe, timeout=3)
    except TimeoutError:
        return Check(name, "down", "timed out", 3000)
    except Exception as exc:
        return Check(name, "down", f"{type(exc).__name__}: {str(exc)[:160]}")
    result.latency_ms = int((time.perf_counter() - started) * 1000)
    return result


async def _http(name: str, url: str, headers: dict[str, str] | None = None) -> Check:
    async with httpx.AsyncClient(timeout=2.5) as client:
        response = await client.get(url, headers=headers or {})
    return Check(
        name, "ok" if response.status_code < 400 else "degraded", f"HTTP {response.status_code}"
    )


async def system_health(session: AsyncSession) -> list[Check]:
    settings = get_settings()

    async def database() -> Check:
        await session.execute(text("SELECT 1"))
        return Check("PostgreSQL", "ok")

    async def redis() -> Check:
        client = get_redis()
        if client is None:
            return Check("Redis", "down", "unavailable (cooling off); rate limits are per-process")
        try:
            await client.ping()
            queue = await client.llen("celery")  # type: ignore[misc]
        except (RedisError, OSError) as exc:
            return Check("Redis", "down", str(exc)[:160])
        return Check("Redis", "ok", extra={"celery_queue_length": queue})

    async def workers() -> Check:
        if settings.task_execution == "inline":
            return Check("Background workers", "off", "inline mode: jobs run inside the API")
        from app.workers.celery_app import celery_app

        replies = await asyncio.to_thread(
            lambda: celery_app.control.inspect(timeout=1.5).ping() or {}
        )
        return Check(
            "Background workers",
            "ok" if replies else "down",
            f"{len(replies)} worker(s) responding",
        )

    async def search() -> Check:
        if settings.search_backend == "database":
            return Check("Meilisearch", "off", "search uses the database")
        key = settings.meili_master_key.get_secret_value() if settings.meili_master_key else None
        return await _http(
            "Meilisearch",
            f"{settings.meili_url.rstrip('/')}/health",
            {"Authorization": f"Bearer {key}"} if key else None,
        )

    async def sandbox() -> Check:
        if settings.code_runner == "fake":
            return Check("Code sandbox", "off", "fake runner (tests)")
        if settings.code_runner == "judge0":
            return await _http("Code sandbox (Judge0)", f"{settings.judge0_url.rstrip('/')}/about")
        check = await _http(
            "Code sandbox (Piston)", f"{settings.piston_url.rstrip('/')}/api/v2/runtimes"
        )
        return check

    async def ollama() -> Check:
        return await _http("Ollama", f"{settings.ollama_base_url.rstrip('/')}/api/tags")

    checks = list(
        await asyncio.gather(
            *(
                _timed(n, p)
                for n, p in (
                    ("PostgreSQL", database()),
                    ("Redis", redis()),
                    ("Background workers", workers()),
                    ("Meilisearch", search()),
                    ("Code sandbox", sandbox()),
                    ("Ollama", ollama()),
                )
            )
        )
    )
    gateway = get_gateway()
    for name in ("github", "openrouter"):
        configured = name in gateway.providers
        checks.append(
            Check(
                f"LLM: {name}",
                "ok" if configured else "off",
                "configured" if configured else "no API key set",
            )
        )
    for provider, breaker in gateway.circuits.items():
        if breaker.state.value != "closed":
            checks.append(
                Check(f"Circuit: {provider}", "degraded", f"circuit {breaker.state.value}")
            )
    return checks


# ------------------------------------------------------------------ failed background jobs

RETRY_WINDOW = timedelta(days=7)


async def failed_jobs(session: AsyncSession) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - RETRY_WINDOW
    items: list[dict[str, Any]] = []
    for resume in await session.scalars(
        select(Resume)
        .where(Resume.status == ResumeStatus.FAILED, Resume.updated_at >= since)
        .limit(50)
    ):
        items.append(
            {
                "kind": "resume_parse",
                "id": str(resume.id),
                "label": resume.original_filename,
                "error": resume.error,
                "at": resume.updated_at,
            }
        )
    for report in await session.scalars(
        select(InterviewReport)
        .where(InterviewReport.status == ReportStatus.FAILED, InterviewReport.updated_at >= since)
        .limit(50)
    ):
        items.append(
            {
                "kind": "interview_report",
                "id": str(report.interview_id),
                "label": "Interview report",
                "error": report.error,
                "at": report.updated_at,
            }
        )
    for attempt in await session.scalars(
        select(FrameworkAttempt)
        .where(
            FrameworkAttempt.status == AttemptStatus.FAILED, FrameworkAttempt.updated_at >= since
        )
        .limit(50)
    ):
        items.append(
            {
                "kind": "framework_grading",
                "id": str(attempt.id),
                "label": f"{attempt.framework_key} test",
                "error": attempt.error,
                "at": attempt.updated_at,
            }
        )
    for item in await session.scalars(
        select(QuestionGeneration)
        .where(
            QuestionGeneration.status == GenerationStatus.FAILED,
            QuestionGeneration.updated_at >= since,
        )
        .limit(50)
    ):
        items.append(
            {
                "kind": "question_generation",
                "id": str(item.id),
                "label": item.topic,
                "error": item.error,
                "at": item.updated_at,
            }
        )
    for run, source_key in (
        await session.execute(
            select(IngestionRun, JobSource.key)
            .join(JobSource, JobSource.id == IngestionRun.source_id)
            .where(
                or_(
                    IngestionRun.status == RunStatus.FAILED,
                    IngestionRun.status == RunStatus.PARTIAL,
                ),
                IngestionRun.started_at >= since,
            )
            .order_by(IngestionRun.started_at.desc())
            .limit(20)
        )
    ).all():
        items.append(
            {
                "kind": "ingestion",
                "id": source_key,
                "label": f"{source_key} ingestion ({run.status.value})",
                "error": "; ".join(run.errors[:2]) if run.errors else None,
                "at": run.started_at,
            }
        )
    items.sort(key=lambda i: i["at"] or datetime.min.replace(tzinfo=UTC), reverse=True)
    return items


async def retry_job(session: AsyncSession, kind: str, item_id: str) -> None:
    from app.workers.runtime import dispatch

    if kind == "resume_parse":
        from app.modules.resumes import service as resumes
        from app.modules.resumes import tasks as resume_tasks

        resume = await session.get(Resume, uuid.UUID(item_id))
        if resume is None:
            raise NotFoundError("Not found")
        await resumes.mark_for_reparse(session, resume)
        await session.commit()
        dispatch(resume_tasks.parse_resume, resumes.parse_resume_job, item_id)
    elif kind == "interview_report":
        from app.modules.interviews import report
        from app.modules.interviews import tasks as interview_tasks

        row = await session.get(InterviewReport, uuid.UUID(item_id))
        if row is None:
            raise NotFoundError("Not found")
        row.status = ReportStatus.PENDING
        await session.commit()
        dispatch(interview_tasks.generate_report, report.generate_report_job, item_id)
    elif kind == "framework_grading":
        from app.modules.skills import service as skills
        from app.modules.skills import tasks as skill_tasks

        attempt = await session.get(FrameworkAttempt, uuid.UUID(item_id))
        if attempt is None:
            raise NotFoundError("Not found")
        attempt.status = AttemptStatus.GRADING
        await session.commit()
        dispatch(skill_tasks.grade_attempt, skills.grade_attempt_job, item_id)
    elif kind == "question_generation":
        from app.modules.coding import generation
        from app.modules.coding import tasks as coding_tasks

        item = await session.get(QuestionGeneration, uuid.UUID(item_id))
        if item is None:
            raise NotFoundError("Not found")
        item.status = GenerationStatus.PENDING
        await session.commit()
        generation.dispatch_generation(coding_tasks, item.id)
    elif kind == "ingestion":
        from app.modules.jobs import tasks as job_tasks
        from app.modules.jobs.ingestion import run_ingestion

        dispatch(job_tasks.ingest_source_task, run_ingestion, item_id, "manual", None)
    else:
        raise AppError(f"Unknown job kind '{kind}'", code="unknown_job")


# ------------------------------------------------------------------ announcements


async def active_announcements(session: AsyncSession, *, is_admin: bool) -> list[Announcement]:
    now = datetime.now(UTC)
    stmt = (
        select(Announcement)
        .where(
            Announcement.active.is_(True),
            or_(Announcement.starts_at.is_(None), Announcement.starts_at <= now),
            or_(Announcement.ends_at.is_(None), Announcement.ends_at > now),
        )
        .order_by(Announcement.created_at.desc())
        .limit(5)
    )
    if not is_admin:
        stmt = stmt.where(Announcement.audience == "all")
    return list(await session.scalars(stmt))
