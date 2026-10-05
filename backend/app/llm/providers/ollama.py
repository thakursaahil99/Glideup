"""Ollama running on the host (http://localhost:11434). Free, local, private."""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.types import CompletionRequest, CompletionResult, EmbeddingResult, LLMError


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        timeout: float,
        client: httpx.AsyncClient | None = None,
        num_ctx: int = 8192,
    ):
        self._base_url = base_url.rstrip("/")
        self._num_ctx = num_ctx
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(f"{self._base_url}{path}", json=payload)
        except httpx.TimeoutException as exc:
            raise LLMError("timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"unreachable: {type(exc).__name__}") from exc
        if response.status_code != 200:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}")
        data: dict[str, Any] = response.json()
        return data

    async def stream(
        self, request: CompletionRequest, model: str
    ) -> AsyncIterator[str | CompletionResult]:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": self._num_ctx,
            },
        }
        parts: list[str] = []
        try:
            async with self._client.stream(
                "POST", f"{self._base_url}/api/chat", json=payload
            ) as response:
                if response.status_code != 200:
                    body = (await response.aread()).decode(errors="replace")
                    raise LLMError(f"HTTP {response.status_code}: {body[:200]}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise LLMError("malformed stream chunk") from exc
                    if data.get("error"):
                        raise LLMError(str(data["error"])[:200])
                    delta = (data.get("message") or {}).get("content") or ""
                    if delta:
                        parts.append(delta)
                        yield delta
                    if data.get("done"):
                        yield CompletionResult(
                            text="".join(parts),
                            provider=self.name,
                            model=model,
                            prompt_tokens=int(data.get("prompt_eval_count") or 0),
                            completion_tokens=int(data.get("eval_count") or 0),
                            latency_ms=int((time.perf_counter() - started) * 1000),
                        )
                        return
        except httpx.TimeoutException as exc:
            raise LLMError("timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"unreachable: {type(exc).__name__}") from exc
        raise LLMError("stream ended without completion")

    async def complete(self, request: CompletionRequest, model: str) -> CompletionResult:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                "num_ctx": self._num_ctx,
            },
        }
        if request.json_output:
            payload["format"] = "json"
        data = await self._post("/api/chat", payload)
        message = data.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise LLMError("malformed response")
        return CompletionResult(
            text=message["content"],
            provider=self.name,
            model=model,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        started = time.perf_counter()
        data = await self._post("/api/embed", {"model": model, "input": texts})
        vectors = data.get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise LLMError("malformed embedding response")
        return EmbeddingResult(
            vectors=[[float(x) for x in v] for v in vectors],
            provider=self.name,
            model=model,
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
