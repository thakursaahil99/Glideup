"""Celery entry points for resume jobs (thin wrappers around the async jobs)."""

from app.modules.resumes.service import embed_resume_job, parse_resume_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="resumes.parse", acks_late=True, max_retries=0)
def parse_resume(resume_id: str) -> None:
    # No Celery-level retries: the LLM gateway already falls back across providers,
    # and a failed parse is visible to the user with a "try again" action.
    run_in_worker_loop(parse_resume_job(resume_id))


@celery_app.task(name="resumes.embed", acks_late=True, max_retries=2, default_retry_delay=30)
def embed_resume(resume_id: str) -> None:
    run_in_worker_loop(embed_resume_job(resume_id))
