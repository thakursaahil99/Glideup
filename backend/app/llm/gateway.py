"""LLM gateway: the single entry point every module uses to talk to models.

routing (task -> ordered provider:model chain)
  -> circuit breaker per provider (skip providers that keep failing)
  -> timeout per call
  -> automatic fallback to the next route on error/timeout/invalid output
  -> structured output: JSON parsed + validated with Pydantic, one repair round per route
  -> every attempt (success or failure) recorded to `llm_usage`
"""

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Protocol, TypeVar

import structlog
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.db.models import LLMUsage
from app.llm.circuit import CircuitRegistry
from app.llm.pricing import estimate_cost
from app.llm.providers.base import LLMProvider
from app.llm.routing import Route, routes_for
from app.llm.types import (
    AllProvidersFailedError,
    Attempt,
    CallContext,
    CompletionRequest,
    CompletionResult,
    EmbeddingResult,
    LLMError,
    Message,
)

logger = structlog.stdlib.get_logger(__name__)

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R", CompletionResult, EmbeddingResult)


class UsageRecorder(Protocol):
    async def record(self, usage: LLMUsage) -> None: ...


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def extract_json(text: str) -> object:
    """Parse a model's JSON answer, tolerating code fences and leading/trailing chatter."""
    cleaned = _FENCE.sub("", text.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


class LLMGateway:
    def __init__(
        self,
        settings: Settings,
        providers: dict[str, LLMProvider],
        recorder: UsageRecorder,
        circuits: CircuitRegistry | None = None,
    ):
        self.settings = settings
        self.providers = providers
        self.recorder = recorder
        self.circuits = circuits or CircuitRegistry(
            settings.circuit_breaker_failure_threshold, settings.circuit_breaker_cooldown_seconds
        )

    # ------------------------------------------------------------------ plumbing

    def _timeout(self, route: Route) -> float:
        return self.settings.llm_provider_timeouts.get(
            route.provider, self.settings.llm_timeout_seconds
        )

    def _usable_routes(self, task: str, ctx: CallContext) -> list[tuple[Route, LLMProvider]]:
        usable = []
        for route in routes_for(task, self.settings):
            provider = self.providers.get(route.provider)
            if provider is None:
                ctx.attempts.append(Attempt(route.provider, route.model, "not configured"))
                continue
            usable.append((route, provider))
        return usable

    async def _call(
        self,
        task: str,
        operation: str,
        route: Route,
        ctx: CallContext,
        fn: Callable[[], Awaitable[R]],
    ) -> R | None:
        breaker = self.circuits.get(route.provider)
        if not breaker.allow():
            ctx.attempts.append(Attempt(route.provider, route.model, "circuit open"))
            return None
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(fn(), timeout=self._timeout(route))
        except (LLMError, TimeoutError) as exc:
            error = "timeout" if isinstance(exc, TimeoutError) else str(exc) or type(exc).__name__
            breaker.record_failure()
            ctx.attempts.append(Attempt(route.provider, route.model, error))
            logger.warning("llm_call_failed", task=task, route=str(route), error=error)
            await self._record(task, operation, route, ctx, started, error=error)
            return None
        breaker.record_success()
        await self._record(task, operation, route, ctx, started, result=result)
        return result

    async def _record(
        self,
        task: str,
        operation: str,
        route: Route,
        ctx: CallContext,
        started: float,
        *,
        result: CompletionResult | EmbeddingResult | None = None,
        error: str | None = None,
    ) -> None:
        prompt_tokens = result.prompt_tokens if result else 0
        completion_tokens = result.completion_tokens if isinstance(result, CompletionResult) else 0
        usage = LLMUsage(
            task=task,
            provider=route.provider,
            model=route.model,
            operation=operation,
            success=error is None,
            error=error[:1000] if error else None,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=int((time.perf_counter() - started) * 1000),
            estimated_cost_usd=estimate_cost(
                route.provider, route.model, prompt_tokens, completion_tokens
            ),
            prompt_version=ctx.prompt_version,
            user_id=ctx.user_id,
            request_id=ctx.request_id,
        )
        try:
            await self.recorder.record(usage)
        except Exception:  # usage logging must never break the user's request
            logger.exception("llm_usage_record_failed")

    # ------------------------------------------------------------------ public API

    async def complete(
        self,
        task: str,
        messages: list[Message],
        *,
        json_output: bool = False,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        ctx: CallContext | None = None,
    ) -> CompletionResult:
        ctx = ctx or CallContext()
        request = CompletionRequest(task, messages, json_output, temperature, max_tokens)
        for route, provider in self._usable_routes(task, ctx):
            result = await self._call(
                task,
                "complete",
                route,
                ctx,
                partial(provider.complete, request, route.model),
            )
            if result is not None:
                return result
        raise AllProvidersFailedError(task, ctx.attempts)

    async def complete_json(
        self,
        task: str,
        messages: list[Message],
        schema: type[T],
        *,
        max_repairs: int = 1,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        ctx: CallContext | None = None,
    ) -> tuple[T, CompletionResult]:
        """Structured output. Invalid JSON gets one repair round on the same model; if it is
        still invalid, the next route is tried (a model that can't follow the schema is
        treated like a failing one)."""
        ctx = ctx or CallContext()
        for route, provider in self._usable_routes(task, ctx):
            conversation = list(messages)
            for repair in range(max_repairs + 1):
                request = CompletionRequest(task, conversation, True, temperature, max_tokens)
                result = await self._call(
                    task,
                    "complete",
                    route,
                    ctx,
                    partial(provider.complete, request, route.model),
                )
                if result is None:
                    break  # provider failed -> next route
                try:
                    return schema.model_validate(extract_json(result.text)), result
                except (json.JSONDecodeError, ValidationError) as exc:
                    problem = str(exc)[:800]
                    logger.info("llm_invalid_output", task=task, route=str(route), repair=repair)
                    if repair == max_repairs:
                        ctx.attempts.append(
                            Attempt(route.provider, route.model, f"invalid output: {problem[:200]}")
                        )
                        break
                    conversation += [
                        Message("assistant", result.text),
                        Message(
                            "user",
                            "That answer was not valid for the required JSON shape. "
                            f"Problems: {problem}\n"
                            "Reply again with ONLY the corrected JSON object.",
                        ),
                    ]
        raise AllProvidersFailedError(task, ctx.attempts)

    async def embed(
        self, texts: list[str], *, task: str = "embedding", ctx: CallContext | None = None
    ) -> EmbeddingResult:
        ctx = ctx or CallContext()
        for route, provider in self._usable_routes(task, ctx):
            result = await self._call(
                task,
                "embed",
                route,
                ctx,
                partial(provider.embed, texts, route.model),
            )
            if result is not None:
                return result
        raise AllProvidersFailedError(task, ctx.attempts)
