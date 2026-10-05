"""Celery entry points for matching (thin wrappers around the async jobs)."""

from app.modules.matching.embeddings import embed_jobs_job
from app.modules.matching.service import analyze_match_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="matching.embed_jobs", acks_late=True, max_retries=0)
def embed_jobs() -> None:
    # Commits per batch and is re-run on a schedule, so no Celery retries are needed.
    run_in_worker_loop(embed_jobs_job())


@celery_app.task(name="matching.analyze", acks_late=True, max_retries=0)
def analyze_match(match_id: str) -> None:
    # The gateway already falls back across providers; a failure is shown with a retry.
    run_in_worker_loop(analyze_match_job(match_id))
