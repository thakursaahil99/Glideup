"""Composition root for the LLM layer: builds providers from settings, once per process."""

import structlog

from app.core.config import Settings, get_settings
from app.db.models import EMBEDDING_DIMENSIONS, LLMUsage
from app.db.session import session_factory
from app.llm.gateway import LLMGateway
from app.llm.providers.base import LLMProvider
from app.llm.providers.mock import MockHandler, MockProvider
from app.llm.providers.ollama import OllamaProvider
from app.llm.providers.openai_compat import OpenAICompatibleProvider

logger = structlog.stdlib.get_logger(__name__)

# Modules register heuristic handlers here (task -> fn) so the mock provider can produce
# useful output for their tasks without the LLM layer depending on those modules.
MOCK_HANDLERS: dict[str, MockHandler] = {}

_gateway: LLMGateway | None = None


class DatabaseUsageRecorder:
    """Writes usage in its own short transaction, so failed calls are recorded even when
    the business transaction that triggered them rolls back."""

    async def record(self, usage: LLMUsage) -> None:
        async with session_factory()() as session:
            session.add(usage)
            await session.commit()


def build_providers(settings: Settings) -> dict[str, LLMProvider]:
    timeout = settings.llm_timeout_seconds
    providers: dict[str, LLMProvider] = {
        "ollama": OllamaProvider(
            settings.ollama_base_url,
            settings.llm_provider_timeouts.get("ollama", timeout),
            num_ctx=settings.ollama_num_ctx,
        ),
        "mock": MockProvider(
            delay_ms=settings.mock_llm_delay_ms,
            error_rate=settings.mock_llm_error_rate,
            dimensions=EMBEDDING_DIMENSIONS,
            handlers=MOCK_HANDLERS,
        ),
    }
    if settings.github_models_token:
        providers["github"] = OpenAICompatibleProvider(
            "github",
            settings.github_models_base_url,
            settings.github_models_token.get_secret_value(),
            timeout,
            embedding_dimensions=EMBEDDING_DIMENSIONS,
        )
    if settings.openrouter_api_key:
        providers["openrouter"] = OpenAICompatibleProvider(
            "openrouter",
            settings.openrouter_base_url,
            settings.openrouter_api_key.get_secret_value(),
            timeout,
            extra_headers={"X-Title": "GlideUp"},
            embedding_dimensions=EMBEDDING_DIMENSIONS,
        )
    return providers


def get_gateway() -> LLMGateway:
    global _gateway
    if _gateway is None:
        settings = get_settings()
        providers = build_providers(settings)
        _gateway = LLMGateway(settings, providers, DatabaseUsageRecorder())
        logger.info("llm_gateway_ready", providers=sorted(providers))
    return _gateway


def set_gateway(gateway: LLMGateway | None) -> None:
    """Tests (and the eval runner) swap in a gateway with fake providers."""
    global _gateway
    _gateway = gateway
