"""Portfolio analysis use-cases: request (API), analyze (background), combined skills."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, ConflictError, NotFoundError
from app.core.safe_fetch import FetchError, UnsafeUrlError, fetch_page, vet_url
from app.db.models import AnalysisStatus, PortfolioAnalysis, PortfolioKind, Profile, User
from app.db.session import session_factory
from app.llm import prompt_store
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.portfolio import website
from app.modules.portfolio.github import analyze_github, username_from_url
from app.modules.portfolio.schemas import ParsedPortfolio, PortfolioResult
from app.modules.profiles import links
from app.modules.resumes import service as resumes
from app.modules.resumes.skills import canonicalize

logger = structlog.stdlib.get_logger(__name__)

# An analysis stuck in "analyzing" longer than this was abandoned (worker killed mid-job).
STALE_ANALYZING_AFTER = timedelta(minutes=10)


class InvalidPortfolioUrlError(AppError):
    status_code = 422
    code = "invalid_portfolio_url"


def _in_progress(analysis: PortfolioAnalysis) -> bool:
    if analysis.status not in (AnalysisStatus.PENDING, AnalysisStatus.ANALYZING):
        return False
    updated = analysis.updated_at.replace(tzinfo=analysis.updated_at.tzinfo or UTC)
    return datetime.now(UTC) - updated < STALE_ANALYZING_AFTER


def classify(raw_url: str) -> tuple[PortfolioKind, str]:
    """Validate a user-typed link and decide how to analyze it."""
    try:
        url = links.normalize_url(raw_url)
    except ValueError as exc:
        raise InvalidPortfolioUrlError(str(exc)) from exc
    if url is None:
        raise InvalidPortfolioUrlError("Enter a link to analyze.")
    if links.is_linkedin(url):
        raise InvalidPortfolioUrlError(
            "LinkedIn doesn't allow profiles to be read automatically. Upload your resume, or "
            "add your GitHub or portfolio site instead.",
            code="linkedin_not_supported",
        )
    if links.is_github(url):
        try:
            username = username_from_url(url)
        except ValueError as exc:
            raise InvalidPortfolioUrlError(str(exc)) from exc
        return PortfolioKind.GITHUB, f"https://github.com/{username}"
    return PortfolioKind.WEBSITE, url


# ------------------------------------------------------------------ queries


async def list_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[PortfolioAnalysis]:
    rows = await session.scalars(
        select(PortfolioAnalysis)
        .where(PortfolioAnalysis.user_id == user_id)
        .order_by(PortfolioAnalysis.kind)
    )
    return list(rows)


async def get_owned(session: AsyncSession, user: User, analysis_id: uuid.UUID) -> PortfolioAnalysis:
    analysis = await session.get(PortfolioAnalysis, analysis_id)
    if analysis is None or analysis.user_id != user.id:
        raise NotFoundError("Analysis not found")  # 404, not 403: don't leak existence
    return analysis


# ------------------------------------------------------------------ commands


async def request_analysis(session: AsyncSession, user: User, raw_url: str) -> PortfolioAnalysis:
    """Create (or restart) the user's analysis for this kind of link. Runs in the background."""
    kind, url = classify(raw_url)
    if kind == PortfolioKind.WEBSITE:
        try:  # fail fast on localhost/IP/private addresses instead of in the background
            await vet_url(url)
        except (UnsafeUrlError, FetchError) as exc:
            raise InvalidPortfolioUrlError(str(exc)) from exc

    analysis = await session.scalar(
        select(PortfolioAnalysis).where(
            PortfolioAnalysis.user_id == user.id, PortfolioAnalysis.kind == kind
        )
    )
    if analysis is not None and _in_progress(analysis):
        raise ConflictError("This link is already being analyzed", code="already_analyzing")
    if analysis is None:
        analysis = PortfolioAnalysis(user_id=user.id, kind=kind, url=url)
        session.add(analysis)
    analysis.url = url
    analysis.status = AnalysisStatus.PENDING
    analysis.error = None

    # The user just told us this is their link: keep the profile in step.
    profile = await session.get(Profile, user.id)
    if profile is None:
        profile = Profile(user_id=user.id, target_roles=[], preferred_locations=[])
        session.add(profile)
    if kind == PortfolioKind.GITHUB:
        profile.github_url = url
    else:
        profile.portfolio_url = url
    await session.flush()
    logger.info("portfolio_analysis_requested", kind=kind.value, analysis_id=str(analysis.id))
    return analysis


async def delete(session: AsyncSession, analysis: PortfolioAnalysis) -> None:
    await session.delete(analysis)
    await session.flush()


# ------------------------------------------------------------------ background job


async def _analyze_website(
    analysis: PortfolioAnalysis, user_id: uuid.UUID
) -> tuple[PortfolioResult, str]:
    settings = get_settings()
    page = await fetch_page(
        analysis.url,
        max_bytes=settings.portfolio_fetch_max_bytes,
        timeout=settings.portfolio_fetch_timeout_seconds,
    )
    text = (
        page.text.strip() if page.content_type == "text/plain" else website.visible_text(page.text)
    )
    if len(text) < website.MIN_TEXT_CHARS:
        raise FetchError(
            "We couldn't read enough text on this site. Sites built entirely with JavaScript "
            "can't be read yet. Try your GitHub link, or upload your resume."
        )
    messages, version = await prompt_store.render("portfolio_parse", url=page.url, site_text=text)
    parsed, result = await get_gateway().complete_json(
        Task.PORTFOLIO_PARSE,
        messages,
        ParsedPortfolio,
        ctx=CallContext(user_id=user_id, prompt_version=version),
    )
    grounded = website.ground(parsed, text)
    return website.to_result(grounded), f"{result.provider}:{result.model}"


async def analyze_job(analysis_id: str) -> None:
    """Fetch and analyze one portfolio link. Idempotent; failures are shown to the user."""
    async with session_factory()() as session:
        analysis = await session.get(PortfolioAnalysis, uuid.UUID(analysis_id))
        if analysis is None or analysis.status not in (
            AnalysisStatus.PENDING,
            AnalysisStatus.ANALYZING,
        ):
            return
        if analysis.status == AnalysisStatus.ANALYZING and _in_progress(analysis):
            return  # another worker has it
        analysis.status = AnalysisStatus.ANALYZING
        analysis.attempts += 1
        await session.commit()
        log = logger.bind(analysis_id=analysis_id, kind=analysis.kind.value)

        blog: str | None = None
        try:
            if analysis.kind == PortfolioKind.GITHUB:
                result, blog = await analyze_github(analysis.url)
                analyzed_by = "github-api"
            else:
                result, analyzed_by = await _analyze_website(analysis, analysis.user_id)
        except (FetchError, UnsafeUrlError) as exc:
            log.info("portfolio_analysis_failed", error=str(exc))
            await _fail(session, analysis, str(exc))
            return
        except AllProvidersFailedError as exc:
            log.warning("portfolio_analysis_failed", error=str(exc))
            await _fail(
                session,
                analysis,
                "Our AI is unavailable right now. Please try again in a few minutes.",
            )
            return

        analysis.result = result.model_dump(mode="json")
        analysis.analyzed_by = analyzed_by
        analysis.analyzed_at = datetime.now(UTC)
        analysis.status = AnalysisStatus.DONE
        await _prefill_profile(session, analysis.user_id, result, blog)
        await session.commit()
        log.info("portfolio_analyzed", skills=len(result.skills), projects=len(result.projects))


async def _prefill_profile(
    session: AsyncSession, user_id: uuid.UUID, result: PortfolioResult, blog: str | None
) -> None:
    """Fill empty profile fields only; never overwrite what the user typed."""
    profile = await session.get(Profile, user_id)
    if profile is None:
        return
    if not profile.headline and result.headline:
        profile.headline = result.headline
    if blog and not profile.portfolio_url:
        try:
            url = links.normalize_url(blog)
        except ValueError:
            url = None
        if url and not links.is_github(url) and not links.is_linkedin(url):
            profile.portfolio_url = url


async def _fail(session: AsyncSession, analysis: PortfolioAnalysis, message: str) -> None:
    analysis.status = AnalysisStatus.FAILED
    analysis.error = message
    await session.commit()


# ------------------------------------------------------------------ combined skills


@dataclass(slots=True)
class CombinedSkill:
    name: str
    normalized: str
    category: str | None
    sources: list[str] = field(default_factory=list)  # "resume", "github", "website"


async def user_skills(session: AsyncSession, user_id: uuid.UUID) -> list[CombinedSkill]:
    """Every skill we know for a user, from the active resume and finished analyses.

    This is the input for job matching: someone with only a GitHub profile still gets
    matched, and a skill confirmed by several sources can be weighted higher.
    """
    combined: dict[str, CombinedSkill] = {}

    def add(name: str, category: str | None, source: str) -> None:
        canonical = canonicalize(name)
        skill = combined.setdefault(
            canonical.normalized,
            CombinedSkill(canonical.name, canonical.normalized, category or canonical.category),
        )
        if source not in skill.sources:
            skill.sources.append(source)

    resume = await resumes.get_active(session, user_id)
    if resume is not None:
        for resume_skill in resume.skills:
            add(resume_skill.name, resume_skill.category, "resume")
    for analysis in await list_for_user(session, user_id):
        if analysis.status == AnalysisStatus.DONE and analysis.result:
            for skill in PortfolioResult.model_validate(analysis.result).skills:
                add(skill.name, skill.category, analysis.kind.value)
    return sorted(combined.values(), key=lambda s: (-len(s.sources), s.name.lower()))
