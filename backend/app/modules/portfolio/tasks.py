"""Celery entry point for portfolio analysis (a thin wrapper around the async job)."""

from app.modules.portfolio.service import analyze_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="portfolio.analyze", acks_late=True, max_retries=0)
def analyze_portfolio(analysis_id: str) -> None:
    # No Celery retries: a failed analysis is shown to the user with a "try again" action.
    run_in_worker_loop(analyze_job(analysis_id))
