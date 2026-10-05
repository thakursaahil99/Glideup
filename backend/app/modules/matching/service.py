"""Job matching: score jobs for a user, recommend jobs, and run AI skill-gap analyses.

Scores are computed on request (a page of jobs costs one vector query plus arithmetic),
so they always reflect the current resume and job. Only the slow LLM analysis is stored,
in `job_matches`, tied to the inputs it was computed from.
"""

import hashlib
import re
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import ColumnElement, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.db.models import (
    ExperienceLevel,
    Job,
    JobMatch,
    MatchAnalysisStatus,
    Profile,
    RemotePreference,
    Resume,
    ResumeStatus,
    WorkMode,
)
from app.db.session import session_factory
from app.jobsources.geo import lookup_metro, metro_cities, parse_location
from app.llm import prompts
from app.llm.factory import get_gateway
from app.llm.routing import Task
from app.llm.types import AllProvidersFailedError, CallContext
from app.modules.matching import embeddings, heuristics  # noqa: F401  (registers the mock)
from app.modules.matching.schemas import SkillGapAnalysis, ground
from app.modules.matching.scoring import MatchResult, cosine, score_match
from app.modules.portfolio.service import user_skills
from app.modules.resumes import service as resumes
from app.modules.resumes.schemas import ParsedResume
from app.modules.resumes.skills import canonicalize
from app.workers.runtime import dispatch

logger = structlog.get_logger(__name__)

RECOMMEND_POOL = 400  # nearest jobs re-ranked with the full score
RECOMMEND_MAX = 200  # results a user can page through
ANALYSIS_STUCK_AFTER = timedelta(minutes=15)
JOB_TEXT_CHARS = 6000  # of the posting given to the LLM
_REEMBED_EVERY_S = 600.0
_reembed_requested: dict[uuid.UUID, float] = {}  # resume id -> monotonic time


class QuotaExceededError(AppError):
    status_code = 429
    code = "quota_exceeded"


class NoProfileDataError(AppError):
    status_code = 409
    code = "no_profile_data"


# ------------------------------------------------------------------ the candidate


@dataclass
class Candidate:
    user_id: uuid.UUID
    resume: Resume | None
    vector: list[float] | None
    have: dict[str, str]  # normalised skill key -> display name
    sources: dict[str, list[str]]  # normalised key -> ["resume", "github", ...]
    years: float | None
    profile: Profile | None
    embedding_pending: bool = False  # a resume exists but its vector isn't usable yet

    @property
    def fingerprint(self) -> str:
        """Changes whenever the inputs to an analysis change."""
        raw = "|".join(
            [str(self.resume.id if self.resume else ""), str(self.years), *sorted(self.have)]
        )
        return hashlib.sha256(raw.encode()).hexdigest()


def _request_resume_embedding(resume: Resume) -> None:
    """Re-embed a resume whose vector is missing or from another model, at most every
    few minutes per resume (Ollama may simply be down)."""
    now = time.monotonic()
    if now - _reembed_requested.get(resume.id, -_REEMBED_EVERY_S) < _REEMBED_EVERY_S:
        return
    _reembed_requested[resume.id] = now
    from app.modules.resumes import tasks

    dispatch(tasks.embed_resume, resumes.embed_resume_job, str(resume.id))


async def load_candidate(session: AsyncSession, user_id: uuid.UUID) -> Candidate | None:
    """Everything we know about the user that matters for fit. None if there's nothing."""
    resume = await resumes.get_active(session, user_id)
    skills = await user_skills(session, user_id)
    profile = await session.get(Profile, user_id)

    vector: list[float] | None = None
    pending = False
    if resume is not None and resume.status == ResumeStatus.PARSED:
        key = embeddings.current_key()
        if resume.embedding is not None and resume.embedding_model == key:
            vector = list(resume.embedding)
        else:
            pending = True
            _request_resume_embedding(resume)

    years: float | None = None
    if profile is not None and profile.years_experience is not None:
        years = float(profile.years_experience)
    elif resume is not None and resume.parsed:
        total = ParsedResume.model_validate(resume.parsed).total_years_experience
        years = float(total) if total is not None else None

    if not skills and vector is None:
        return None
    return Candidate(
        user_id=user_id,
        resume=resume,
        vector=vector,
        have={s.normalized: s.name for s in skills},
        sources={s.normalized: list(s.sources) for s in skills},
        years=years,
        profile=profile,
        embedding_pending=pending,
    )


# ------------------------------------------------------------------ scoring


async def score_jobs(
    session: AsyncSession, candidate: Candidate, jobs: Sequence[Job]
) -> dict[uuid.UUID, MatchResult]:
    vectors: dict[uuid.UUID, list[float]] = {}
    key = embeddings.current_key()
    if candidate.vector is not None and key is not None:
        vectors = await embeddings.job_vectors(session, [j.id for j in jobs], key)
    results: dict[uuid.UUID, MatchResult] = {}
    for job in jobs:
        vector = vectors.get(job.id)
        result = score_match(
            similarity=cosine(candidate.vector, vector)
            if candidate.vector is not None and vector is not None
            else None,
            job_skills=job.skills,
            have=candidate.have,
            level=job.experience_level,
            years=candidate.years,
        )
        if result is not None:
            results[job.id] = result
    return results


async def scores_for_user(
    session: AsyncSession, user_id: uuid.UUID, jobs: Sequence[Job]
) -> dict[uuid.UUID, MatchResult]:
    candidate = await load_candidate(session, user_id)
    return await score_jobs(session, candidate, jobs) if candidate else {}


def practice_stack(job: Job) -> tuple[list[str], list[str]]:
    """Languages and frameworks a skill test for this job should pre-select."""
    languages: list[str] = []
    frameworks: list[str] = []
    for raw in job.skills:
        skill = canonicalize(raw)
        if skill.category == "language" and skill.name not in ("HTML", "CSS", "SQL", "Bash"):
            languages.append(skill.name)
        elif skill.category == "framework":
            frameworks.append(skill.name)
    return languages[:4], frameworks[:4]


# ------------------------------------------------------------------ recommendations


@dataclass
class Preferences:
    cities: set[str] = field(default_factory=set)
    states: set[str] = field(default_factory=set)
    countries: set[str] = field(default_factory=set)
    remote: RemotePreference = RemotePreference.ANY

    @classmethod
    def from_profile(cls, profile: Profile | None) -> "Preferences":
        prefs = cls()
        if profile is None:
            return prefs
        prefs.remote = profile.remote_preference
        for text_ in profile.preferred_locations or []:
            if metro := lookup_metro(text_):
                prefs.cities.update(metro_cities(metro))
                continue
            for place in parse_location(text_).places:
                if place.city:
                    prefs.cities.add(place.city)
                elif place.state:
                    prefs.states.add(place.state)
                elif place.country:
                    prefs.countries.add(place.country)
        return prefs


@dataclass
class Recommendation:
    job: Job
    match: MatchResult
    rank: float
    reasons: list[str]


def _aware(moment: datetime | None) -> datetime | None:
    """SQLite (tests) hands back naive datetimes; they are UTC."""
    return moment.replace(tzinfo=UTC) if moment and moment.tzinfo is None else moment


def _rank(
    job: Job, match: MatchResult, prefs: Preferences, now: datetime
) -> tuple[float, list[str]]:
    """The match score plus small nudges for what the user said they want."""
    rank = float(match.score)
    reasons: list[str] = []
    total = len(match.matched) + len(match.transferable) + len(match.missing)
    if total and match.matched:
        reasons.append(f"You have {len(match.matched)} of {total} skills it asks for")

    city = next((c for c in job.cities if c in prefs.cities), None)
    state = next((s for s in job.states if s in prefs.states), None)
    if city:
        rank += 6
        reasons.append(f"In {city}, one of your preferred locations")
    elif state:
        rank += 4
        reasons.append(f"In {state}, one of your preferred locations")
    elif any(c in prefs.countries for c in job.countries):
        rank += 2

    if prefs.remote == RemotePreference.REMOTE:
        if job.work_mode == WorkMode.REMOTE:
            rank += 5
            reasons.append("Remote, as you prefer")
        elif job.work_mode == WorkMode.ONSITE:
            rank -= 8
    elif prefs.remote in (RemotePreference.HYBRID, RemotePreference.ONSITE) and (
        job.work_mode == prefs.remote.value
    ):
        rank += 3

    posted = _aware(job.posted_at or job.first_seen_at)
    if posted and now - posted < timedelta(days=14):
        rank += 2
        reasons.append("Posted in the last two weeks")
    return rank, reasons


# A trailing "(...)" or a part after the last -, en/em dash, |, comma or slash.
_TRAILING_PART = re.compile(
    r"\s*(?:\(([^()]*)\)|[-\u2013\u2014|,/]\s*([^-\u2013\u2014|,/()]+))\s*$"
)


def role_title(title: str) -> str:
    """The title without a trailing location: "SWE - Mexico" and "SWE (London)" -> "swe"."""
    text_ = " ".join(title.split())
    while match := _TRAILING_PART.search(text_):
        part = (match.group(1) or match.group(2) or "").strip()
        parsed = parse_location(part)
        if not part or not (parsed.places or parsed.remote):
            break
        text_ = text_[: match.start()].rstrip()
    return text_.casefold()


def _listed() -> tuple[ColumnElement[bool], ...]:
    return (Job.is_active.is_(True), Job.is_hidden.is_(False), Job.duplicate_of_id.is_(None))


def _filters(countries: Sequence[str], remote_only: bool) -> list[ColumnElement[bool]]:
    """Applied inside the candidate search, so a narrow filter still gets a full pool."""
    clauses: list[ColumnElement[bool]] = list(_listed())
    if countries:
        clauses.append(or_(*[Job.location_index.contains(f"|c:{c}|") for c in countries]))
    if remote_only:
        clauses.append(Job.work_mode == WorkMode.REMOTE)
    return clauses


async def _candidate_pool(
    session: AsyncSession, candidate: Candidate, filters: list[ColumnElement[bool]]
) -> list[uuid.UUID]:
    key = embeddings.current_key()
    if candidate.vector is not None and key is not None:
        dialect = session.bind.dialect.name if session.bind else ""
        if dialect == "postgresql":
            # If the planner picks the HNSW index, it returns only ef_search candidates
            # *before* the filters apply (pgvector < 0.8); widen it so filters can't starve
            # the pool. At today's size the planner uses an exact scan (~30 ms) anyway.
            await session.execute(text("SET LOCAL hnsw.ef_search = 1000"))
            rows = await session.scalars(
                select(Job.id)
                .where(*filters, Job.embedding_model == key)
                .order_by(Job.embedding.cosine_distance(candidate.vector))
                .limit(RECOMMEND_POOL)
            )
            return list(rows)
        # SQLite (tests): exact search in Python.
        rows_ = await session.execute(
            select(Job.id, Job.embedding).where(*filters, Job.embedding_model == key)
        )
        scored = sorted(
            ((cosine(candidate.vector, list(v)), i) for i, v in rows_ if v is not None),
            reverse=True,
        )
        return [i for _, i in scored[:RECOMMEND_POOL]]

    # No usable resume vector: jobs that mention the user's skills, newest first.
    if not candidate.have:
        return []
    terms = [Job.skills_index.contains(f"|{name.lower()}|") for name in candidate.have.values()]
    rows2 = await session.scalars(
        select(Job.id)
        .where(*filters, or_(*terms))
        .order_by(Job.posted_at.desc().nulls_last())
        .limit(RECOMMEND_POOL * 3)
    )
    return list(rows2)


async def recommend(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    countries: Sequence[str] = (),
    remote_only: bool = False,
) -> tuple[Candidate | None, list[Recommendation]]:
    """Ranked recommendations (best first), capped at RECOMMEND_MAX."""
    candidate = await load_candidate(session, user_id)
    if candidate is None:
        return None, []
    ids = await _candidate_pool(session, candidate, _filters(countries, remote_only))
    if not ids:
        return candidate, []
    jobs = list(await session.scalars(select(Job).where(Job.id.in_(ids))))
    matches = await score_jobs(session, candidate, jobs)
    prefs = Preferences.from_profile(candidate.profile)
    now = datetime.now(UTC)
    ranked: list[Recommendation] = []
    for job in jobs:
        match = matches.get(job.id)
        if match is None:
            continue
        rank, reasons = _rank(job, match, prefs, now)
        ranked.append(Recommendation(job, match, rank, reasons))
    ranked.sort(key=lambda r: (-r.rank, -r.match.score, str(r.job.id)))
    # One entry per role: companies often post the same opening once per country/city.
    seen: set[tuple[str, str]] = set()
    unique: list[Recommendation] = []
    for rec in ranked:
        role = (rec.job.company_name.casefold(), role_title(rec.job.title))
        if role not in seen:
            seen.add(role)
            unique.append(rec)
    return candidate, unique[:RECOMMEND_MAX]


# ------------------------------------------------------------------ AI skill-gap analysis


def _is_fresh(row: JobMatch, job: Job, candidate: Candidate) -> bool:
    return (
        row.resume_id == (candidate.resume.id if candidate.resume else None)
        and row.job_content_hash == job.content_hash
        and row.skills_fingerprint == candidate.fingerprint
        and row.prompt_version == prompts.ACTIVE_VERSIONS["skill_gap"]
    )


@dataclass
class MatchView:
    candidate: Candidate | None
    match: MatchResult | None
    analysis: JobMatch | None
    analysis_stale: bool


async def match_view(session: AsyncSession, user_id: uuid.UUID, job: Job) -> MatchView:
    candidate = await load_candidate(session, user_id)
    if candidate is None:
        return MatchView(None, None, None, False)
    match = (await score_jobs(session, candidate, [job])).get(job.id)
    row = await session.scalar(
        select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job.id)
    )
    return MatchView(candidate, match, row, row is not None and not _is_fresh(row, job, candidate))


async def request_analysis(session: AsyncSession, user_id: uuid.UUID, job: Job) -> JobMatch:
    """Start (or reuse) an AI skill-gap analysis. Idempotent while one is fresh or running."""
    candidate = await load_candidate(session, user_id)
    if candidate is None:
        raise NoProfileDataError(
            "Upload your resume (or connect GitHub) first, so we know your skills."
        )
    now = datetime.now(UTC)
    row = await session.scalar(
        select(JobMatch).where(JobMatch.user_id == user_id, JobMatch.job_id == job.id)
    )
    if row is not None and _is_fresh(row, job, candidate):
        running = row.status in (MatchAnalysisStatus.PENDING, MatchAnalysisStatus.ANALYZING)
        requested = _aware(row.requested_at) or now
        if row.status == MatchAnalysisStatus.DONE or (
            running and now - requested < ANALYSIS_STUCK_AFTER
        ):
            return row

    limit = get_settings().match_analysis_daily_limit
    used = await session.scalar(
        select(func.count())
        .select_from(JobMatch)
        .where(JobMatch.user_id == user_id, JobMatch.requested_at >= now - timedelta(days=1))
    )
    if (used or 0) >= limit:
        raise QuotaExceededError(
            f"You've used today's {limit} AI analyses. Match scores and skill lists still "
            "work; try the AI analysis again tomorrow."
        )

    match = (await score_jobs(session, candidate, [job])).get(job.id)
    if row is None:
        row = JobMatch(user_id=user_id, job_id=job.id)
        session.add(row)
    row.resume_id = candidate.resume.id if candidate.resume else None
    row.status = MatchAnalysisStatus.PENDING
    row.score = match.score if match else None
    row.error = None
    row.job_content_hash = job.content_hash
    row.skills_fingerprint = candidate.fingerprint
    row.prompt_version = prompts.ACTIVE_VERSIONS["skill_gap"]
    row.requested_at = now
    await session.commit()

    from app.modules.matching import tasks

    dispatch(tasks.analyze_match, analyze_match_job, str(row.id))
    return row


def _candidate_text(candidate: Candidate) -> str:
    lines: list[str] = []
    parsed = (
        ParsedResume.model_validate(candidate.resume.parsed)
        if candidate.resume is not None and candidate.resume.parsed
        else None
    )
    if parsed and parsed.headline:
        lines.append(f"Headline: {parsed.headline}")
    if candidate.years is not None:
        lines.append(f"Years of experience: {candidate.years:g}")
    years_by_skill = {
        s.normalized: s.years for s in (candidate.resume.skills if candidate.resume else [])
    }
    skills = []
    for key, name in sorted(candidate.have.items(), key=lambda kv: kv[1].lower()):
        years = years_by_skill.get(key)
        skills.append(f"{name} ({years:g} yrs)" if years is not None else name)
    lines.append("Skills: " + (", ".join(skills) if skills else "none listed"))
    if parsed:
        for role in parsed.experience[:4]:
            lines.append(f"- {role.title} at {role.company}: " + "; ".join(role.highlights[:2]))
    return "\n".join(lines)


async def analyze_match_job(match_id: str) -> None:
    """Background job: run the LLM skill-gap analysis for one JobMatch row."""
    async with session_factory()() as session:
        row = await session.get(JobMatch, uuid.UUID(match_id))
        if row is None or row.status not in (
            MatchAnalysisStatus.PENDING,
            MatchAnalysisStatus.ANALYZING,
        ):
            return
        job = await session.get(Job, row.job_id)
        candidate = await load_candidate(session, row.user_id)
        if job is None or candidate is None:
            row.status = MatchAnalysisStatus.FAILED
            row.error = "The job or your profile data is no longer available."
            await session.commit()
            return
        row.status = MatchAnalysisStatus.ANALYZING
        await session.commit()

        match = (await score_jobs(session, candidate, [job])).get(job.id)
        job_text = job.description_text[:JOB_TEXT_CHARS]
        messages, version = prompts.render(
            "skill_gap",
            title=job.title,
            company=job.company_name,
            level=job.experience_level.value
            if job.experience_level != ExperienceLevel.UNKNOWN
            else None,
            job_skills=job.skills,
            missing=match.missing if match else [],
            job_text=f"{job.title}\n{job_text}",
            candidate=_candidate_text(candidate),
        )
        ctx = CallContext(user_id=row.user_id, prompt_version=version)
        try:
            analysis, result = await get_gateway().complete_json(
                Task.SKILL_GAP, messages, SkillGapAnalysis, ctx=ctx, max_tokens=1500
            )
        except AllProvidersFailedError as exc:
            logger.warning("skill_gap_failed", match_id=match_id, error=str(exc))
            row.status = MatchAnalysisStatus.FAILED
            row.error = "Our AI coach is unavailable right now. Please try again in a few minutes."
            await session.commit()
            return

        grounded = ground(
            analysis,
            job_text=f"{job.title}\n{job.description_text}",
            job_skills=job.skills,
            candidate_skills=set(candidate.have),
        )
        row.analysis = grounded.model_dump(mode="json")
        row.analyzed_by = f"{result.provider}:{result.model}"
        row.analyzed_at = datetime.now(UTC)
        row.status = MatchAnalysisStatus.DONE
        await session.commit()
        logger.info(
            "skill_gap_done",
            match_id=match_id,
            by=row.analyzed_by,
            missing=len(grounded.missing),
            dropped=len(analysis.missing) - len(grounded.missing),
        )


async def get_listed_job(session: AsyncSession, job_id: uuid.UUID) -> Job:
    job = await session.get(Job, job_id)
    if job is None or job.is_hidden:
        raise NotFoundError("Job not found")
    return job
