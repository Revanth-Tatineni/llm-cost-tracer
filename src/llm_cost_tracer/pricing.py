"""Per-model USD pricing, in dollars per 1,000,000 tokens. This table goes stale the moment a
provider changes prices -- that's expected; update it and bump PRICING_LAST_UPDATED rather than
treating it as load-bearing for anything beyond an approximate cost estimate.
"""

from __future__ import annotations

PRICING_LAST_UPDATED = "2026-10-23"

# provider -> model -> (input $ / 1M tokens, output $ / 1M tokens)
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-opus-5": (15.0, 75.0),
        "claude-sonnet-5": (3.0, 15.0),
        "claude-haiku-4-5": (0.80, 4.0),
    },
    "openai": {
        "gpt-4o": (2.50, 10.0),
        "gpt-4o-mini": (0.15, 0.60),
    },
}


class UnknownPricingError(KeyError):
    """Raised by calculate_cost when there's no rate for provider/model and no fallback_rate
    was given -- callers choose whether that should crash or just cost $0 (see tracer.py)."""


def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    fallback_rate: tuple[float, float] | None = None,
) -> float:
    """Dollar cost for a call, given its token counts. `fallback_rate` (input $/1M, output
    $/1M) is used when the model isn't in PRICING -- e.g. a brand-new model release."""
    rates = PRICING.get(provider, {}).get(model)
    if rates is None:
        if fallback_rate is None:
            raise UnknownPricingError(
                f"No pricing for {provider}/{model}; pass fallback_rate=(input_$/1M, output_$/1M) "
                "or add it with register_pricing()"
            )
        rates = fallback_rate
    input_rate, output_rate = rates
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate


def register_pricing(provider: str, model: str, input_rate: float, output_rate: float) -> None:
    """Add or override a rate at runtime -- for a model not yet in the built-in table, or a
    price change, without waiting on a new llm-cost-tracer release."""
    PRICING.setdefault(provider, {})[model] = (input_rate, output_rate)
