"""Per-provider circuit breaker.

closed --(N consecutive failures)--> open --(cooldown elapsed)--> half-open
half-open lets exactly one trial call through: success closes, failure re-opens.

State is per process. That's enough to stop each worker hammering a dead provider;
Phase 9 can move it to Redis if cross-process sharing is worth it.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)

    _failures: int = 0
    _opened_at: float | None = None
    _trial_in_flight: bool = False

    def _now(self) -> float:
        return self.clock()

    @property
    def state(self) -> CircuitState:
        if self._opened_at is None:
            return CircuitState.CLOSED
        if self._now() - self._opened_at >= self.cooldown_seconds:
            return CircuitState.HALF_OPEN
        return CircuitState.OPEN

    def allow(self) -> bool:
        state = self.state
        if state is CircuitState.CLOSED:
            return True
        if state is CircuitState.HALF_OPEN and not self._trial_in_flight:
            self._trial_in_flight = True
            return True
        return False

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None
        self._trial_in_flight = False

    def record_failure(self) -> None:
        self._trial_in_flight = False
        self._failures += 1
        if self._opened_at is not None or self._failures >= self.failure_threshold:
            self._opened_at = self._now()


class CircuitRegistry:
    def __init__(self, failure_threshold: int, cooldown_seconds: float):
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, provider: str) -> CircuitBreaker:
        if provider not in self._breakers:
            self._breakers[provider] = CircuitBreaker(self._threshold, self._cooldown)
        return self._breakers[provider]

    def snapshot(self) -> dict[str, str]:
        return {name: breaker.state.value for name, breaker in self._breakers.items()}
