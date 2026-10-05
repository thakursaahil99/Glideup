"""Celery application. Workers: `celery -A app.workers.celery_app worker`;
scheduler: `celery -A app.workers.celery_app beat`.

Schedules are added per module in later phases (e.g. job ingestion every 6 hours).
"""

from celery import Celery
from celery.signals import setup_logging

from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()

celery_app = Celery("glideup", broker=settings.broker_url, backend=settings.result_backend)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,  # a task is re-delivered if the worker dies mid-run...
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # ...and long LLM tasks don't hog the queue
    task_track_started=True,
    result_expires=60 * 60 * 24,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # Cheap check; each source has its own admin-editable schedule (default 6 hours).
        "ingest-due-job-sources": {"task": "jobs.ingest_due", "schedule": 300.0},
        # Embeds new/changed jobs; ingestion also triggers it, this catches up after outages.
        "embed-pending-jobs": {"task": "matching.embed_jobs", "schedule": 900.0},
        # Finishes interviews whose time ran out with nobody connected (and queues reports).
        "expire-interviews": {"task": "interviews.expire", "schedule": 300.0},
    },
)
celery_app.conf.include = [
    "app.workers.tasks",
    "app.modules.resumes.tasks",
    "app.modules.portfolio.tasks",
    "app.modules.jobs.tasks",
    "app.modules.matching.tasks",
    "app.modules.interviews.tasks",
    "app.modules.coding.tasks",
    "app.modules.skills.tasks",
]


@setup_logging.connect
def _configure_celery_logging(**_: object) -> None:
    configure_logging(settings.log_level, json=settings.log_json)
