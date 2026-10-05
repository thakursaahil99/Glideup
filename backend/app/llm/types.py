"""Provider-neutral request/response types for the LLM layer."""

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str


@dataclass(frozen=True, slots=True)
class CompletionRequest:
    task: str
    messages: list[Message]
    json_output: bool = False
    temperature: float = 0.2
    max_tokens: int = 2048


@dataclass(frozen=True, slots=True)
class CompletionResult:
    text: str
    provider: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: list[list[float]]
    provider: str
    model: str
    prompt_tokens: int = 0
    latency_ms: int = 0


@dataclass(frozen=True, slots=True)
class Attempt:
    provider: str
    model: str
    error: str


@dataclass(slots=True)
class CallContext:
    """Who/what a call is for — recorded with usage."""

    user_id: object | None = None
    request_id: str | None = None
    prompt_version: str | None = None
    attempts: list[Attempt] = field(default_factory=list)


class LLMError(Exception):
    """A provider call failed (network, HTTP error, timeout, bad payload)."""


class ProviderNotConfiguredError(LLMError):
    pass


class AllProvidersFailedError(LLMError):
    def __init__(self, task: str, attempts: list[Attempt]):
        summary = (
            "; ".join(f"{a.provider}:{a.model} -> {a.error}" for a in attempts) or "no providers"
        )
        super().__init__(f"All providers failed for task '{task}': {summary}")
        self.task = task
        self.attempts = attempts


class InvalidOutputError(LLMError):
    """The model answered, but not with output matching the requested schema."""


class StreamInterruptedError(LLMError):
    """A streamed answer broke off after text was already sent to the user. Falling back
    to another model mid-answer would repeat or contradict it, so the caller decides."""

    def __init__(self, task: str, partial: str, reason: str):
        super().__init__(f"Stream for task '{task}' interrupted: {reason}")
        self.task = task
        self.partial = partial
        self.reason = reason


class BudgetExceededError(AllProvidersFailedError):
    """The user's daily AI token budget is used up (AI / LLM Settings)."""

    def __init__(self, task: str):
        super().__init__(task, [Attempt("budget", "-", "daily token budget reached")])
