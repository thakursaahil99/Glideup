from typing import Protocol

from app.llm.types import CompletionRequest, CompletionResult, EmbeddingResult


class LLMProvider(Protocol):
    """Every model backend (Ollama, GitHub Models, OpenRouter, Mock, later Azure OpenAI)
    implements this. The gateway handles routing, fallback, retries and usage logging,
    so providers stay thin: translate the request, call the API, translate the answer."""

    name: str

    async def complete(self, request: CompletionRequest, model: str) -> CompletionResult: ...

    async def embed(self, texts: list[str], model: str) -> EmbeddingResult: ...
