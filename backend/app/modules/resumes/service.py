"""Resume use-cases: upload, parse (background), edit, activate, delete."""

import hashlib
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.storage import ObjectNotFoundError, resume_storage
from app.db.models import EMBEDDING_DIMENSIONS, Profile, Resume, ResumeSkill, ResumeStatus, User
from app.db.session import session_factory
from app.llm import prompts
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.resumes import heuristics  # noqa: F401  (registers the mock parser)
from app.modules.resumes.grounding import ground
from app.modules.resumes.pdf import InvalidPdfError, extract_text, inspect_pdf
from app.modules.resumes.schemas import ParsedResume
from app.modules.resumes.skills import canonicalize

logger = structlog.stdlib.get_logger(__name__)

MAX_RESUMES_PER_USER = 10
MIN_TEXT_CHARS = 200
# A resume stuck in "parsing" longer than this was abandoned (worker killed mid-job):
# a redelivered job or the user's "try again" may reclaim it.
STALE_PARSING_AFTER = timedelta(minutes=10)


def _parsing_in_progress(resume: Resume) -> bool:
    if resume.status != ResumeStatus.PARSING:
        return False
    updated = resume.updated_at.replace(tzinfo=resume.updated_at.tzinfo or UTC)
    return datetime.now(UTC) - updated < STALE_PARSING_AFTER


class ResumeTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"


class InvalidResumeError(AppError):
    status_code = 422
    code = "invalid_resume"


def _safe_filename(filename: str | None) -> str:
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    name = re.sub(r"[^\w.\- ()]+", "_", name)[:200]
    return name if name.lower().endswith(".pdf") else f"{name or 'resume'}.pdf"


# ------------------------------------------------------------------ queries


async def get_owned(session: AsyncSession, user: User, resume_id: uuid.UUID) -> Resume:
    resume = await session.get(Resume, resume_id)
    if resume is None or resume.user_id != user.id:
        raise NotFoundError("Resume not found")  # 404, not 403: don't leak existence
    return resume


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[Resume]:
    rows = await session.scalars(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())
    )
    return list(rows)


async def get_active(session: AsyncSession, user_id: uuid.UUID) -> Resume | None:
    return await session.scalar(
        select(Resume).where(Resume.user_id == user_id, Resume.is_active.is_(True))
    )


async def _set_active(session: AsyncSession, resume: Resume) -> None:
    # Deactivate first and flush: the partial unique index allows one active row per user.
    await session.execute(
        update(Resume)
        .where(Resume.user_id == resume.user_id, Resume.id != resume.id)
        .values(is_active=False)
    )
    await session.flush()
    resume.is_active = True
    await session.flush()


# ------------------------------------------------------------------ commands


async def upload(
    session: AsyncSession, user: User, *, filename: str | None, data: bytes
) -> tuple[Resume, bool]:
    """Store a new resume and make it active. Returns (resume, created).

    Uploading the exact same file again returns the existing resume (idempotent).
    """
    settings = get_settings()
    if len(data) > settings.resume_max_bytes:
        raise ResumeTooLargeError(
            f"Resumes can be at most {settings.resume_max_bytes // (1024 * 1024)} MB."
        )
    try:
        info = inspect_pdf(data, max_pages=settings.resume_max_pages)
    except InvalidPdfError as exc:
        raise InvalidResumeError(str(exc)) from exc

    digest = hashlib.sha256(data).hexdigest()
    existing = await session.scalar(
        select(Resume).where(Resume.user_id == user.id, Resume.sha256 == digest)
    )
    if existing is not None:
        await _set_active(session, existing)
        return existing, False

    count = await session.scalar(select(func.count()).where(Resume.user_id == user.id)) or 0
    if count >= MAX_RESUMES_PER_USER:
        raise ConflictError(
            f"You can keep up to {MAX_RESUMES_PER_USER} resumes. Delete an old one first.",
            code="too_many_resumes",
        )

    resume_id = uuid.uuid4()
    key = f"users/{user.id}/{resume_id}.pdf"
    await resume_storage().put(key, data, "application/pdf")
    resume = Resume(
        id=resume_id,
        user_id=user.id,
        original_filename=_safe_filename(filename),
        storage_key=key,
        content_type="application/pdf",
        size_bytes=len(data),
        sha256=digest,
        page_count=info.page_count,
        status=ResumeStatus.UPLOADED,
    )
    session.add(resume)
    await session.flush()
    await _set_active(session, resume)
    logger.info("resume_uploaded", resume_id=str(resume.id), pages=info.page_count)
    return resume, True


async def mark_for_reparse(session: AsyncSession, resume: Resume) -> None:
    if _parsing_in_progress(resume):
        raise ConflictError("This resume is already being parsed", code="already_parsing")
    resume.status = ResumeStatus.UPLOADED
    resume.error = None
    await session.flush()


async def update_parsed(session: AsyncSession, resume: Resume, parsed: ParsedResume) -> Resume:
    if resume.status != ResumeStatus.PARSED:
        raise ConflictError("Wait for parsing to finish before editing", code="not_parsed")
    _apply_parsed(resume, parsed)
    resume.user_edited_at = datetime.now(UTC)
    resume.embedding = None  # stale until the embed job refreshes it
    await session.flush()
    await session.refresh(resume, ["skills"])
    return resume


async def activate(session: AsyncSession, resume: Resume) -> Resume:
    await _set_active(session, resume)
    return resume


async def delete(session: AsyncSession, resume: Resume) -> None:
    was_active = resume.is_active
    user_id, key = resume.user_id, resume.storage_key
    await session.delete(resume)
    await session.flush()
    if was_active:
        newest = await session.scalar(
            select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())
        )
        if newest is not None:
            await _set_active(session, newest)
    try:
        await resume_storage().delete(key)
    except Exception:  # the row is gone; an orphaned object is cleaned up later
        logger.exception("resume_file_delete_failed", key=key)


def _apply_parsed(resume: Resume, parsed: ParsedResume) -> None:
    resume.parsed = parsed.model_dump(mode="json")
    existing = {s.normalized: s for s in resume.skills}
    wanted: dict[str, ResumeSkill] = {}
    for skill in parsed.skills:
        canonical = canonicalize(skill.name)
        row = existing.get(canonical.normalized) or ResumeSkill(normalized=canonical.normalized)
        row.name = canonical.name
        row.category = skill.category or canonical.category
        row.years = Decimal(str(skill.years)) if skill.years is not None else None
        row.level = skill.level
        wanted[canonical.normalized] = row
    resume.skills = list(wanted.values())


def embedding_text(parsed: ParsedResume) -> str:
    """What we embed: the parts of a resume that describe fit for a job."""
    parts = [parsed.headline or "", parsed.summary or ""]
    parts.append("Skills: " + ", ".join(s.name for s in parsed.skills))
    for job in parsed.experience[:6]:
        parts.append(f"{job.title} at {job.company}. " + " ".join(job.highlights[:3]))
    return "\n".join(p for p in parts if p.strip())[:8000]


async def _prefill_profile(session: AsyncSession, user_id: uuid.UUID, parsed: ParsedResume) -> None:
    """Fill empty profile fields from the resume; never overwrite what the user typed."""
    profile = await session.get(Profile, user_id)
    if profile is None:
        profile = Profile(user_id=user_id, target_roles=[], preferred_locations=[])
        session.add(profile)
    if not profile.headline and parsed.headline:
        profile.headline = parsed.headline
    if profile.years_experience is None and parsed.total_years_experience is not None:
        profile.years_experience = Decimal(str(parsed.total_years_experience))
    if not profile.preferred_locations and parsed.location:
        profile.preferred_locations = [parsed.location]


# ------------------------------------------------------------------ background jobs


async def parse_resume_job(resume_id: str) -> None:
    """Extract text -> LLM structured parse -> skills -> embedding. Idempotent."""
    async with session_factory()() as session:
        resume = await session.get(Resume, uuid.UUID(resume_id))
        if resume is None or resume.status == ResumeStatus.PARSED or _parsing_in_progress(resume):
            return
        resume.status = ResumeStatus.PARSING
        resume.parse_attempts += 1
        resume.error = None
        await session.commit()
        log = logger.bind(resume_id=resume_id, user_id=str(resume.user_id))

        try:
            data = await resume_storage().get(resume.storage_key)
        except ObjectNotFoundError:
            await _fail(session, resume, "The uploaded file is missing. Please upload it again.")
            return

        text = extract_text(data)
        if len(text) < MIN_TEXT_CHARS:
            await _fail(
                session,
                resume,
                "We couldn't read text from this PDF. Scanned or image-only PDFs aren't "
                "supported yet — please upload a PDF exported from Word or Google Docs.",
            )
            return
        resume.raw_text = text

        messages, version = prompts.render(
            "resume_parse", resume_text=text, today=date.today().isoformat()
        )
        ctx = CallContext(user_id=resume.user_id, prompt_version=version)
        try:
            parsed, result = await get_gateway().complete_json(
                Task.RESUME_PARSE, messages, ParsedResume, ctx=ctx
            )
        except AllProvidersFailedError as exc:
            log.warning("resume_parse_failed", error=str(exc))
            await _fail(
                session,
                resume,
                "Our AI parser is unavailable right now. Please try again in a few minutes.",
            )
            return

        parsed = ground(parsed, text)
        _apply_parsed(resume, parsed)
        resume.parsed_by = f"{result.provider}:{result.model}"
        resume.parsed_at = datetime.now(UTC)
        resume.status = ResumeStatus.PARSED
        await _prefill_profile(session, resume.user_id, parsed)
        await session.commit()
        log.info("resume_parsed", parsed_by=resume.parsed_by, skills=len(parsed.skills))

    await embed_resume_job(resume_id)


async def embed_resume_job(resume_id: str) -> None:
    """(Re)compute the resume embedding. A failure here never fails the parse."""
    async with session_factory()() as session:
        resume = await session.get(Resume, uuid.UUID(resume_id))
        if resume is None or resume.parsed is None:
            return
        parsed = ParsedResume.model_validate(resume.parsed)
        try:
            result = await get_gateway().embed(
                [embedding_text(parsed)], ctx=CallContext(user_id=resume.user_id)
            )
        except AllProvidersFailedError as exc:
            logger.warning("resume_embed_failed", resume_id=resume_id, error=str(exc))
            return
        vector = result.vectors[0]
        if len(vector) != EMBEDDING_DIMENSIONS:
            logger.error(
                "embedding_dimension_mismatch", got=len(vector), expected=EMBEDDING_DIMENSIONS
            )
            return
        resume.embedding = vector
        resume.embedding_model = f"{result.provider}:{result.model}"
        await session.commit()


async def _fail(session: AsyncSession, resume: Resume, message: str) -> None:
    resume.status = ResumeStatus.FAILED
    resume.error = message
    await session.commit()
