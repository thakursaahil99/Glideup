"""Periodic jobs over HTTP, for hosts without Celery Beat (serverless). An external scheduler
(GitHub Actions, Vercel Cron) calls this with the shared CRON_SECRET."""

import hmac
from typing import Annotated

import structlog
from fastapi import APIRouter, Header

from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.modules.interviews.service import expire_due_job
from app.modules.jobs.ingestion import ingest_due_sources
from app.modules.matching.embeddings import embed_jobs_job
from app.modules.tracker.service import send_due_reminders_job

logger = structlog.stdlib.get_logger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


@router.post("/cron")
async def run_periodic_jobs(
    authorization: Annotated[str, Header()] = "",
) -> dict[str, object]:
    secret = get_settings().cron_secret
    expected = f"Bearer {secret.get_secret_value()}" if secret else ""
    if not secret or not hmac.compare_digest(authorization, expected):
        raise NotFoundError("Not found")  # don't advertise the endpoint
    results: dict[str, object] = {}
    for name, job in (
        ("interviews_expired", expire_due_job),
        ("reminders_sent", send_due_reminders_job),
        ("ingestions_started", ingest_due_sources),
        ("embeddings", embed_jobs_job),
    ):
        try:
            results[name] = await job()
        except Exception as exc:  # one failing job must not stop the others
            logger.exception("cron_job_failed", job=name)
            results[name] = f"error: {type(exc).__name__}"
    return results
