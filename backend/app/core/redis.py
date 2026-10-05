"""Shared async Redis client for rate limiting and caching.

Redis is an accelerator here, never a single point of failure: calls use short timeouts,
and after a failure Redis is treated as down for a cool-off period so requests don't each
wait on a dead connection. Callers fall back (in-memory limits, no cache).
"""

import time

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

COOL_OFF_S = 30.0
_client: Redis | None = None
_down_until = 0.0


def get_redis() -> Redis | None:
    """The client, or None while Redis is considered down."""
    global _client
    if time.monotonic() < _down_until:
        return None
    if _client is None:
        _client = Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=0.25,
            socket_timeout=0.5,
            decode_responses=True,
        )
    return _client


def mark_down(error: Exception) -> None:
    global _down_until
    if time.monotonic() >= _down_until:
        logger.warning("redis_unavailable", error=str(error), cool_off_s=COOL_OFF_S)
    _down_until = time.monotonic() + COOL_OFF_S


def reset() -> None:
    """Tests: forget the client and any down state."""
    global _client, _down_until
    _client = None
    _down_until = 0.0


__all__ = ["RedisError", "get_redis", "mark_down", "reset"]
