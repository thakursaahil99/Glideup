"""Celery entry points for job ingestion."""

from app.modules.jobs.ingestion import ingest_due_sources, run_ingestion
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="jobs.ingest_source", acks_late=True, max_retries=0)
def ingest_source_task(
    source_key: str, trigger: str = "schedule", actor_id: str | None = None
) -> None:
    # No Celery retries: the HTTP client already retries each request, and the next
    # scheduled run picks up anything that failed.
    run_in_worker_loop(run_ingestion(source_key, trigger, actor_id))


@celery_app.task(name="jobs.ingest_due")
def ingest_due() -> list[str]:
    return run_in_worker_loop(ingest_due_sources())
