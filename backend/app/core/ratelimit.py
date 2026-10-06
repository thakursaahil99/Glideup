"""Token-bucket rate limiting, per user and per endpoint group.

Buckets live in Redis, updated atomically by a Lua script, so limits hold across API
workers. If Redis is unavailable we fall back to an in-process bucket: limits then apply
per worker (looser), but the API keeps serving. Rejections return 429 with Retry-After.
"""

import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request

from app.api.deps import get_current_user
from app.core.errors import AppError
from app.core.metrics import RATE_LIMITED
from app.core.redis import RedisError, get_redis, mark_down
from app.db.models import User

# KEYS[1]: bucket; ARGV: capacity, refill per second, now (s), cost. Returns {allowed, wait_ms}.
_LUA = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local cost = tonumber(ARGV[4])
local state = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(state[1]) or capacity
local ts = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + (now - ts) * rate)
local allowed = 0
local wait = 0
if tokens >= cost then
  tokens = tokens - cost
  allowed = 1
else
  wait = math.ceil((cost - tokens) / rate * 1000)
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000) + 1000)
return {allowed, wait}
"""


@dataclass(frozen=True)
class Limit:
    capacity: int  # burst
    per_minute: float  # sustained refill

    @property
    def rate(self) -> float:
        return self.per_minute / 60.0


# Endpoint groups. LLM- and sandbox-backed actions are much stricter than reads.
LIMITS: dict[str, Limit] = {
    "default": Limit(capacity=120, per_minute=300),
    "llm": Limit(capacity=6, per_minute=12),  # AI analyses, interview setup, playground
    "code": Limit(capacity=10, per_minute=20),  # run / submit
    "upload": Limit(capacity=5, per_minute=5),
    "auth": Limit(capacity=10, per_minute=10),  # password sign-in / register, per email
    "interview": Limit(capacity=20, per_minute=30),  # live interview messages (LLM turns)
}


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"


_local: dict[str, tuple[float, float]] = {}  # key -> (tokens, last refill)


def _take_local(key: str, limit: Limit, now: float) -> tuple[bool, int]:
    tokens, ts = _local.get(key, (float(limit.capacity), now))
    tokens = min(limit.capacity, tokens + (now - ts) * limit.rate)
    if tokens >= 1:
        _local[key] = (tokens - 1, now)
        return True, 0
    _local[key] = (tokens, now)
    return False, math.ceil((1 - tokens) / limit.rate * 1000)


async def take(bucket: str, subject: str, limit: Limit | None = None) -> tuple[bool, int]:
    """Spend one token. Returns (allowed, retry_after_ms)."""
    limit = limit or LIMITS[bucket]
    key = f"rl:{bucket}:{subject}"
    now = time.time()
    redis = get_redis()
    if redis is not None:
        try:
            args = (str(limit.capacity), str(limit.rate), str(now), "1")
            allowed, wait = await redis.eval(_LUA, 1, key, *args)  # type: ignore[misc]
            return bool(int(allowed)), int(wait)
        except (RedisError, OSError) as exc:
            mark_down(exc)
    return _take_local(key, limit, time.monotonic())


async def enforce(bucket: str, subject: str) -> None:
    allowed, wait_ms = await take(bucket, subject)
    if not allowed:
        RATE_LIMITED.labels(bucket).inc()
        seconds = max(1, math.ceil(wait_ms / 1000))
        raise RateLimitedError(
            f"Too many requests. Please wait {seconds} second{'s' if seconds != 1 else ''}.",
            details={"retry_after": seconds},
        )


def rate_limit(bucket: str) -> Callable[..., Awaitable[None]]:
    """Dependency: limit the signed-in user on this endpoint group."""

    async def dependency(user: Annotated[User, Depends(get_current_user)]) -> None:
        await enforce(bucket, str(user.id))

    return dependency


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    return (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else "?")
    )


def reset_local() -> None:
    _local.clear()
