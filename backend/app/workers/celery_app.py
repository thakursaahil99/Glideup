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
    beat_schedule={},
)
celery_app.autodiscover_tasks(["app.workers"], related_name="tasks")


@setup_logging.connect
def _configure_celery_logging(**_: object) -> None:
    configure_logging(settings.log_level, json=settings.log_json)
