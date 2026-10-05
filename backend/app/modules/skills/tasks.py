"""Celery entry points for skills (thin wrappers around the async jobs)."""

from app.modules.skills.service import grade_attempt_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="skills.grade_attempt", acks_late=True, max_retries=0)
def grade_attempt(attempt_id: str) -> None:
    # A failed grading is shown to the user with a "try again" action.
    run_in_worker_loop(grade_attempt_job(attempt_id))
