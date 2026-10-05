"""Any OpenAI-compatible chat API: GitHub Models, OpenRouter — and later Azure OpenAI."""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm.types import CompletionRequest, CompletionResult, EmbeddingResult, LLMError


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: str,
        timeout: float,
        extra_headers: dict[str, str] | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        self.name = name
        self._base_url = base_url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {api_key}", **(extra_headers or {})}
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = await self._client.post(
                f"{self._base_url}{path}", json=payload, headers=self._headers
            )
        except httpx.TimeoutException as exc:
            raise LLMError("timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"unreachable: {type(exc).__name__}") from exc
        if response.status_code == 429:
            raise LLMError("rate limited (429)")
        if response.status_code >= 400:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}")
        data: dict[str, Any] = response.json()
        return data

    async def complete(self, request: CompletionRequest, model: str) -> CompletionResult:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.json_output:
            payload["response_format"] = {"type": "json_object"}
        data = await self._post("/chat/completions", payload)
        try:
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed response") from exc
        if not isinstance(text, str):
            raise LLMError("empty response")
        return CompletionResult(
            text=text,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def stream(
        self, request: CompletionRequest, model: str
    ) -> AsyncIterator[str | CompletionResult]:
        """Server-sent events; usage arrives in a final chunk (`include_usage`)."""
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        parts: list[str] = []
        usage: dict[str, Any] = {}
        try:
            async with self._client.stream(
                "POST", f"{self._base_url}/chat/completions", json=payload, headers=self._headers
            ) as response:
                if response.status_code == 429:
                    raise LLMError("rate limited (429)")
                if response.status_code >= 400:
                    body = (await response.aread()).decode(errors="replace")
                    raise LLMError(f"HTTP {response.status_code}: {body[:200]}")
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data_text = line[5:].strip()
                    if data_text == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_text)
                    except json.JSONDecodeError as exc:
                        raise LLMError("malformed stream chunk") from exc
                    usage = chunk.get("usage") or usage
                    for choice in chunk.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content") or ""
                        if delta:
                            parts.append(delta)
                            yield delta
        except httpx.TimeoutException as exc:
            raise LLMError("timeout") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"unreachable: {type(exc).__name__}") from exc
        if not parts:
            raise LLMError("empty response")
        yield CompletionResult(
            text="".join(parts),
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )

    async def embed(self, texts: list[str], model: str) -> EmbeddingResult:
        started = time.perf_counter()
        data = await self._post("/embeddings", {"model": model, "input": texts})
        try:
            rows = sorted(data["data"], key=lambda r: r["index"])
            vectors = [[float(x) for x in row["embedding"]] for row in rows]
        except (KeyError, TypeError) as exc:
            raise LLMError("malformed embedding response") from exc
        usage = data.get("usage") or {}
        return EmbeddingResult(
            vectors=vectors,
            provider=self.name,
            model=model,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            latency_ms=int((time.perf_counter() - started) * 1000),
        )
