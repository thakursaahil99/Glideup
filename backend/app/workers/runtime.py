"""How background jobs run.

Jobs are plain `async def` functions that open their own DB session. They run either:
- in a Celery worker (TASK_EXECUTION=celery): the task wrapper drives the coroutine on one
  long-lived event loop per worker process, so the async DB pool and HTTP clients are reused;
- inline in the API process (TASK_EXECUTION=inline): scheduled on the running event loop,
  for development without Redis and for tests.

Always dispatch AFTER committing the transaction that created the job's input, otherwise
the job can start before its rows are visible.
"""

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, Protocol

import structlog

from app.core.config import get_settings

logger = structlog.stdlib.get_logger(__name__)

_worker_loop: asyncio.AbstractEventLoop | None = None
_inline_tasks: set[asyncio.Task[Any]] = set()


class _CeleryTask(Protocol):
    def delay(self, *args: Any) -> object: ...


def run_in_worker_loop[T](coro: Coroutine[Any, Any, T]) -> T:
    """Celery task bodies call this to execute an async job."""
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coro)


async def _guarded(name: str, job: Callable[..., Awaitable[Any]], *args: Any) -> None:
    try:
        await job(*args)
    except Exception:
        logger.exception("inline_job_failed", job=name)


def dispatch(celery_task: _CeleryTask, job: Callable[..., Awaitable[Any]], *args: Any) -> None:
    if get_settings().task_execution == "inline":
        task = asyncio.get_running_loop().create_task(_guarded(job.__name__, job, *args))
        _inline_tasks.add(task)
        task.add_done_callback(_inline_tasks.discard)
        return
    celery_task.delay(*args)


async def drain_inline_jobs() -> None:
    """Wait for inline jobs to finish (tests; graceful shutdown)."""
    while _inline_tasks:
        await asyncio.gather(*list(_inline_tasks), return_exceptions=True)
