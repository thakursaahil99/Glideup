"""A polite HTTP client for job sources: rate limited, retried with backoff, identified.

- Requests are spaced to the source's configured rate (admin-editable).
- 429 / 5xx / network errors are retried with exponential backoff and jitter, honouring
  `Retry-After`. Other 4xx are not retried (a wrong board token stays wrong).
"""

import asyncio
import random
import time
from typing import Any

import httpx

USER_AGENT = "GlideUp/0.1 (job-search portfolio project; respects source rate limits)"
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class SourceHttpError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class SourceHttpClient:
    def __init__(
        self,
        *,
        rate_limit_per_minute: int,
        max_retries: int = 3,
        base_delay: float = 1.0,
        timeout: float = 30.0,
        client: httpx.AsyncClient | None = None,
        sleep: Any = asyncio.sleep,
    ):
        self._interval = 60.0 / max(rate_limit_per_minute, 1)
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._client = client or httpx.AsyncClient(
            timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True
        )
        self._owns_client = client is None
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._next_slot = 0.0
        self.requests_made = 0

    async def _wait_for_slot(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._next_slot - now
            self._next_slot = max(now, self._next_slot) + self._interval
        if wait > 0:
            await self._sleep(wait)

    def _backoff(self, attempt: int, retry_after: str | None) -> float:
        if retry_after and retry_after.isdigit():
            return float(min(float(retry_after), 120.0))
        jitter = random.uniform(0, self._base_delay)  # noqa: S311 - not security sensitive
        return float(self._base_delay * (2**attempt) + jitter)

    async def get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        for attempt in range(self._max_retries + 1):
            await self._wait_for_slot()
            self.requests_made += 1
            try:
                response = await self._client.get(url, params=params)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                if attempt == self._max_retries:
                    raise SourceHttpError(f"network error: {type(exc).__name__}") from exc
                await self._sleep(self._backoff(attempt, None))
                continue
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as exc:
                    raise SourceHttpError("response was not JSON", 200) from exc
            if response.status_code in RETRYABLE_STATUS and attempt < self._max_retries:
                await self._sleep(self._backoff(attempt, response.headers.get("retry-after")))
                continue
            raise SourceHttpError(f"HTTP {response.status_code}", response.status_code)
        raise SourceHttpError("retries exhausted")  # pragma: no cover - loop always returns/raises

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
