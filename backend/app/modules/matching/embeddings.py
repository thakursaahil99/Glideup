"""Embeddings for matching: what text we embed, and the job-embedding backfill.

Resumes and jobs must be embedded by the *same* model, with the same text recipe, or their
vectors are not comparable. Every stored vector therefore carries a key such as
`ollama:nomic-embed-text#t1` (provider:model#text-version). Matching only compares
vectors with identical keys; anything else is treated as "not embedded yet".

nomic-embed-text is trained with task prefixes: the resume is the *query* and jobs are the
*documents* it searches. Other models ignore the prefixes harmlessly.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from sqlalchemy import ColumnElement, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import EMBEDDING_DIMENSIONS, ExperienceLevel, Job
from app.db.session import get_engine, session_factory
from app.llm.factory import get_gateway
from app.llm.routing import Task, routes_for
from app.llm.types import AllProvidersFailedError

logger = structlog.get_logger(__name__)

# Bump when the text recipe below changes: every vector is then re-embedded.
TEXT_VERSION = "t1"
QUERY_PREFIX = "search_query: "
DOCUMENT_PREFIX = "search_document: "
DESCRIPTION_CHARS = 1500  # the opening of a posting says what the role is; keeps CPU cost low
BATCH_SIZE = 32
_LOCK_ID = 0x6A6F6273  # pg advisory lock: one backfill at a time across workers


def embedding_key(provider: str, model: str) -> str:
    return f"{provider}:{model}#{TEXT_VERSION}"


def current_key() -> str | None:
    """Key of the primary embedding route. Only vectors from it are stored or compared, so
    a temporary fallback to another model can't mix vector spaces."""
    routes = routes_for(Task.EMBEDDING, get_settings())
    return embedding_key(routes[0].provider, routes[0].model) if routes else None


def resume_query_text(text_: str) -> str:
    return QUERY_PREFIX + text_


def job_document_text(
    title: str,
    company: str,
    level: ExperienceLevel | str,
    skills: Sequence[str],
    description: str,
) -> str:
    parts = [f"{title} at {company}"]
    if level and level != ExperienceLevel.UNKNOWN:
        parts.append(f"Level: {level}")
    if skills:
        parts.append("Skills: " + ", ".join(skills))
    if description:
        parts.append(description[:DESCRIPTION_CHARS])
    return DOCUMENT_PREFIX + "\n".join(parts)


@dataclass
class EmbedStats:
    embedded: int = 0
    skipped: bool = False  # another backfill holds the lock
    stopped_reason: str | None = None


def _pending(key: str) -> tuple[ColumnElement[bool], ...]:
    return (
        Job.is_active.is_(True),
        Job.is_hidden.is_(False),
        Job.duplicate_of_id.is_(None),
        or_(
            Job.embedded_hash.is_(None),
            Job.embedded_hash != Job.content_hash,
            Job.embedding_model.is_(None),
            Job.embedding_model != key,
        ),
    )


async def count_pending(session: AsyncSession) -> int:
    key = current_key()
    if key is None:
        return 0
    return await session.scalar(select(func.count()).select_from(Job).where(*_pending(key))) or 0


async def _embed_batch(session: AsyncSession, key: str, limit: int) -> int | str:
    """Embed up to `limit` pending jobs. Returns how many, or a reason to stop."""
    rows = (
        await session.execute(
            select(
                Job.id,
                Job.title,
                Job.company_name,
                Job.experience_level,
                Job.skills,
                Job.description_text,
                Job.content_hash,
            )
            .where(*_pending(key))
            .order_by(Job.posted_at.desc().nulls_last(), Job.id)
            .limit(limit)
        )
    ).all()
    # End the read transaction before the slow model call: holding it open for seconds
    # blocks schema changes (and everything that queues behind them).
    await session.commit()
    if not rows:
        return 0
    texts = [
        job_document_text(r.title, r.company_name, r.experience_level, r.skills, r.description_text)
        for r in rows
    ]
    try:
        result = await get_gateway().embed(texts)
    except AllProvidersFailedError as exc:
        return f"embedding provider unavailable: {exc}"
    got = embedding_key(result.provider, result.model)
    if got != key:
        return f"primary embedding model unavailable (answered by {got})"
    if len(result.vectors) != len(rows) or any(
        len(v) != EMBEDDING_DIMENSIONS for v in result.vectors
    ):
        return "embedding response had the wrong shape"
    await session.execute(
        update(Job),
        [
            {"id": r.id, "embedding": v, "embedding_model": key, "embedded_hash": r.content_hash}
            for r, v in zip(rows, result.vectors, strict=True)
        ],
    )
    await session.commit()
    return len(rows)


async def embed_pending_jobs(limit: int | None = None) -> EmbedStats:
    """Embed listed jobs that are new, changed, or embedded by another model. Newest first;
    commits per batch, so an interrupted run keeps its progress."""
    stats = EmbedStats()
    key = current_key()
    if key is None:
        stats.stopped_reason = "no embedding route configured"
        return stats
    engine = get_engine()
    async with engine.connect() as lock_conn:
        if engine.dialect.name == "postgresql":
            locked = await lock_conn.scalar(
                text("SELECT pg_try_advisory_lock(:id)"), {"id": _LOCK_ID}
            )
            if not locked:
                stats.skipped = True
                return stats
        try:
            async with session_factory()() as session:
                while limit is None or stats.embedded < limit:
                    size = BATCH_SIZE if limit is None else min(BATCH_SIZE, limit - stats.embedded)
                    outcome = await _embed_batch(session, key, size)
                    if isinstance(outcome, str):
                        stats.stopped_reason = outcome
                        logger.warning(
                            "job_embedding_stopped", reason=outcome, embedded=stats.embedded
                        )
                        break
                    if outcome == 0:
                        break
                    stats.embedded += outcome
        finally:
            if engine.dialect.name == "postgresql":
                await lock_conn.execute(text("SELECT pg_advisory_unlock(:id)"), {"id": _LOCK_ID})
    if stats.embedded:
        logger.info("jobs_embedded", count=stats.embedded, model=key)
    return stats


async def embed_jobs_job() -> None:
    """Background entry point (Celery task / inline)."""
    await embed_pending_jobs()


async def job_vectors(
    session: AsyncSession, job_ids: Sequence[uuid.UUID], key: str
) -> dict[uuid.UUID, list[float]]:
    """Stored vectors for these jobs, only where they came from `key`."""
    if not job_ids:
        return {}
    rows = await session.execute(
        select(Job.id, Job.embedding).where(
            Job.id.in_(list(job_ids)), Job.embedding_model == key, Job.embedding.is_not(None)
        )
    )
    return {job_id: list(vector) for job_id, vector in rows if vector is not None}
