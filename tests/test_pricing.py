from __future__ import annotations

import pytest

from llm_cost_tracer.pricing import UnknownPricingError, calculate_cost, register_pricing


def test_known_model_cost():
    cost = calculate_cost(
        "anthropic", "claude-sonnet-5", input_tokens=1_000_000, output_tokens=1_000_000
    )
    assert cost == pytest.approx(3.0 + 15.0)


def test_zero_tokens_cost_zero():
    assert calculate_cost("anthropic", "claude-sonnet-5", 0, 0) == 0.0


def test_unknown_model_without_fallback_raises():
    with pytest.raises(UnknownPricingError):
        calculate_cost("anthropic", "made-up-model", 100, 100)


def test_unknown_model_with_fallback():
    cost = calculate_cost(
        "anthropic", "made-up-model", 1_000_000, 1_000_000, fallback_rate=(1.0, 2.0)
    )
    assert cost == pytest.approx(3.0)


def test_register_pricing_adds_a_rate():
    register_pricing("custom", "my-model", 1.0, 2.0)
    assert calculate_cost("custom", "my-model", 1_000_000, 1_000_000) == pytest.approx(3.0)
