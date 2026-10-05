"""Exact-match LLM response cache in Redis.

Only for deterministic extraction/grading tasks: the same prompt (same template version,
same inputs) at low temperature should give the same answer, so re-parsing an unchanged
resume or re-grading an identical answer costs nothing. Conversational tasks (the live
interviewer, hints) and creative ones (question generation) are never cached.
"""

import hashlib
import json

from app.core.metrics import LLM_CACHE
from app.core.redis import RedisError, get_redis, mark_down
from app.llm import runtime
from app.llm.types import Message

CACHEABLE_TASKS = {
    "resume_parse",
    "portfolio_parse",
    "skill_gap",
    "interview_plan",
    "interview_report",
    "framework_grade",
}
MAX_TEMPERATURE = 0.3


def cache_key(task: str, messages: list[Message], temperature: float, schema: str) -> str:
    payload = json.dumps(
        [task, schema, round(temperature, 2), [(m.role, m.content) for m in messages]],
        ensure_ascii=False,
    )
    return "llmc:" + hashlib.sha256(payload.encode()).hexdigest()


def eligible(task: str, temperature: float) -> bool:
    return (
        bool(runtime.get("llm.cache_enabled"))
        and task in CACHEABLE_TASKS
        and temperature <= MAX_TEMPERATURE
    )


async def lookup(task: str, key: str) -> dict[str, str] | None:
    redis = get_redis()
    if redis is None:
        return None
    try:
        raw = await redis.get(key)
    except (RedisError, OSError) as exc:
        mark_down(exc)
        return None
    LLM_CACHE.labels(task, "hit" if raw else "miss").inc()
    if not raw:
        return None
    try:
        value: dict[str, str] = json.loads(raw)
        return value
    except json.JSONDecodeError:
        return None


async def store(key: str, text: str, provider: str, model: str) -> None:
    redis = get_redis()
    if redis is None:
        return
    ttl = int(float(runtime.get("llm.cache_ttl_hours") or 24) * 3600)
    try:
        await redis.set(
            key, json.dumps({"text": text, "provider": provider, "model": model}), ex=ttl
        )
    except (RedisError, OSError) as exc:
        mark_down(exc)
