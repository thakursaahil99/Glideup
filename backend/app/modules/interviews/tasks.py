"""Celery entry points for interviews (thin wrappers around the async jobs)."""

from app.modules.interviews.report import generate_report_job
from app.modules.interviews.service import expire_due_job, prepare_interview_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="interviews.prepare", acks_late=True, max_retries=0)
def prepare_interview(interview_id: str) -> None:
    # The planner already falls back to a deterministic plan, so no retries are needed.
    run_in_worker_loop(prepare_interview_job(interview_id))


@celery_app.task(name="interviews.report", acks_late=True, max_retries=0)
def generate_report(interview_id: str) -> None:
    # A failed report is shown to the user with a "try again" action.
    run_in_worker_loop(generate_report_job(interview_id))


@celery_app.task(name="interviews.expire")
def expire_due() -> int:
    return run_in_worker_loop(expire_due_job())
