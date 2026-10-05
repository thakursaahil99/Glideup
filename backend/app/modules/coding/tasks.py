"""Celery entry points for coding practice (thin wrappers around the async jobs)."""

from app.modules.coding.generation import generate_job
from app.modules.coding.service import grade_submission_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="coding.grade", acks_late=True, max_retries=0)
def grade_submission(submission_id: str) -> None:
    run_in_worker_loop(grade_submission_job(submission_id))


@celery_app.task(name="coding.generate_question", acks_late=True, max_retries=0)
def generate_question(item_id: str) -> None:
    run_in_worker_loop(generate_job(item_id))
