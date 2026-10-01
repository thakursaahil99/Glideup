"""Deterministic mock provider for tests, load tests, chaos tests and LLM-free development.

- Configurable latency and error rate (to exercise fallback and circuit breaking).
- Completions are produced by per-task handlers registered by the modules (e.g. a
  heuristic resume parser), so the app stays usable without any real model.
- Embeddings use feature hashing: texts that share words get similar vectors, which keeps
  similarity search meaningful in development.
"""

import asyncio
import hashlib
import json
import math
import random
import re
import time
from collections.abc import Callable

from app.llm.types import CompletionRequest, CompletionResult, EmbeddingResult, LLMError

MockHandler = Callable[[CompletionRequest], str]

_TOKEN = re.compile(r"[a-z0-9+#.]+")


def hashed_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for token in _TOKEN.findall(text.lower()):
        digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "little") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector)) or 1.0
    return [v / norm for v in vector]


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


class MockProvider:
    name = "mock"

    def __init__(
        self,
        *,
        delay_ms: int = 0,
        error_rate: float = 0.0,
        dimensions: int = 768,
        handlers: dict[str, MockHandler] | None = None,
        seed: int | None = None,
    ):
        self.delay_ms = delay_ms
        self.error_rate = error_rate
        self.dimensions = dimensions
        # Kept by reference: modules may register handlers after the provider is built.
        self.handlers = handlers if handlers is not None else {}
        self._random = random.Random(seed)  # noqa: S311 - simulation, not security

    async def _simulate(self) -> None:
        if self.delay_ms:
            await asyncio.sleep(self.delay_ms / 1000)
        if self.error_rate and self._random.random() < self.error_rate:
            raise LLMError("mock: injected failure")

    async def complete(self, request: CompletionRequest, model: str) -> CompletionResult:
        started = time.perf_counter()
        await self._simulate()
        handler = self.handlers.get(request.task)
        if handler is not None:
            text = handler(request)
        elif request.json_output:
            text = json.dumps({"mock": True, "task": request.task})
        else:
            text = f"[mock response for {request.task}]"
        prompt = " ".join(m.content for m in request.messages)
        return CompletionResult(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=_estimate_tokens(prompt),
            completion_tokens=_estimate_tokens(text),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        started = time.perf_counter()
        await self._simulate()
        return EmbeddingResult(
            vectors=[hashed_embedding(t, self.dimensions) for t in texts],
            provider=self.name,
            model=model,
            prompt_tokens=sum(_estimate_tokens(t) for t in texts),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
