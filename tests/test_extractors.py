from __future__ import annotations

from types import SimpleNamespace

from llm_cost_tracer.extractors import (
    extract_anthropic,
    extract_openai,
    extract_tokens,
    register_extractor,
)


def test_extract_anthropic_from_object():
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=120, output_tokens=45))
    assert extract_anthropic(response) == (120, 45)


def test_extract_anthropic_from_dict():
    response = {"usage": {"input_tokens": 10, "output_tokens": 5}}
    assert extract_anthropic(response) == (10, 5)


def test_extract_anthropic_missing_usage_returns_none():
    assert extract_anthropic(object()) is None


def test_extract_openai_from_object():
    response = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=30, completion_tokens=12))
    assert extract_openai(response) == (30, 12)


def test_extract_tokens_dispatches_by_provider():
    response = SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=2))
    assert extract_tokens("anthropic", response) == (1, 2)
    assert extract_tokens("unknown-provider", response) is None


def test_register_extractor_adds_a_provider():
    register_extractor("fake", lambda r: (7, 8))
    assert extract_tokens("fake", object()) == (7, 8)
