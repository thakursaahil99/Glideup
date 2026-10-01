"""Cross-cutting tasks. Module-specific tasks live next to their module from Phase 2 on."""

from app.workers.celery_app import celery_app


@celery_app.task(name="system.ping")
def ping() -> str:
    """Used by health checks and smoke tests to prove a worker is consuming the queue."""
    return "pong"
