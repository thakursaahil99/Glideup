"""Estimated cost per call, in USD.

GlideUp runs on free tiers, so the real bill is $0 — but tracking what each call *would*
cost on a paid deployment (e.g. Azure OpenAI) keeps the cost model visible from day one.
Prices: USD per 1M tokens (input, output). Unknown models count as free.
"""

from decimal import Decimal

PRICES_PER_MILLION: dict[str, tuple[Decimal, Decimal]] = {
    "github:openai/gpt-4.1-mini": (Decimal("0.40"), Decimal("1.60")),
    "github:openai/gpt-4.1": (Decimal("2.00"), Decimal("8.00")),
    "github:openai/text-embedding-3-small": (Decimal("0.02"), Decimal("0")),
}

_MILLION = Decimal(1_000_000)


def estimate_cost(provider: str, model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    price_in, price_out = PRICES_PER_MILLION.get(f"{provider}:{model}", (Decimal(0), Decimal(0)))
    cost = (price_in * prompt_tokens + price_out * completion_tokens) / _MILLION
    return cost.quantize(Decimal("0.000001"))
