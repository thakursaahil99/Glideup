"""Minimal in-process scheduler for TASK_EXECUTION=inline (development without Celery Beat).

Production uses Celery Beat; this exists so a laptop without Docker still refreshes jobs.
"""

import asyncio
import contextlib
from collections.abc import AsyncIterator

import structlog

from app.core.config import Settings

logger = structlog.stdlib.get_logger(__name__)


async def _loop(minutes: int) -> None:
    from app.modules.jobs.ingestion import ingest_due_sources  # avoid import cycles at startup

    while True:
        await asyncio.sleep(minutes * 60)
        try:
            started = await ingest_due_sources()
            if started:
                logger.info("inline_scheduler_started_ingestion", sources=started)
        except Exception:
            logger.exception("inline_scheduler_failed")


@contextlib.asynccontextmanager
async def inline_scheduler(settings: Settings) -> AsyncIterator[None]:
    enabled = (
        settings.task_execution == "inline"
        and settings.inline_scheduler_minutes > 0
        and settings.environment != "test"
    )
    task = asyncio.create_task(_loop(settings.inline_scheduler_minutes)) if enabled else None
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
