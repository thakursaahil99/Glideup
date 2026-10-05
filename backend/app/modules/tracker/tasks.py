"""Celery entry point for reminder emails."""

from app.modules.tracker.service import send_due_reminders_job
from app.workers.celery_app import celery_app
from app.workers.runtime import run_in_worker_loop


@celery_app.task(name="tracker.send_reminders")
def send_reminders() -> int:
    return run_in_worker_loop(send_due_reminders_job())
