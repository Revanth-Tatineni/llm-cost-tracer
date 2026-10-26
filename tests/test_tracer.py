from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from llm_cost_tracer.tracer import current_trace, trace, trace_call


def test_sync_decorator_records_a_call(storage):
    @trace(provider="anthropic", model="claude-sonnet-5", operation="t", storage=storage)
    def generate(prompt: str):
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=5))

    generate("hi")

    rows = storage.query()
    assert len(rows) == 1
    assert rows[0].input_tokens == 10
    assert rows[0].output_tokens == 5
    assert rows[0].cost_usd > 0
    assert rows[0].status == "ok"


async def test_async_decorator_records_a_call(storage):
    @trace(provider="anthropic", model="claude-sonnet-5", operation="t", storage=storage)
    async def generate(prompt: str):
        await asyncio.sleep(0)
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    await generate("hi")

    rows = storage.query()
    assert len(rows) == 1


def test_decorator_records_error_and_reraises(storage):
    @trace(provider="anthropic", model="claude-sonnet-5", operation="t", storage=storage)
    def failing():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        failing()

    rows = storage.query()
    assert rows[0].status == "error"
    assert "boom" in rows[0].error


def test_context_manager_allows_manual_quality_and_metadata(storage):
    with trace_call(
        provider="anthropic", model="claude-sonnet-5", operation="t", storage=storage
    ) as ctx:
        ctx.set_tokens(10, 10)
        ctx.set_quality(0.8)
        ctx.add_metadata(user_id="u1")

    rows = storage.query()
    assert rows[0].quality_score == 0.8
    assert rows[0].metadata_json["user_id"] == "u1"


def test_current_trace_is_none_outside_a_trace():
    assert current_trace() is None


def test_current_trace_is_set_inside_a_trace(storage):
    seen = {}

    @trace(provider="anthropic", model="claude-sonnet-5", operation="t", storage=storage)
    def generate():
        seen["ctx"] = current_trace()
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    generate()
    assert seen["ctx"] is not None
    assert current_trace() is None


def test_unknown_model_pricing_does_not_crash(storage):
    @trace(provider="anthropic", model="unreleased-model", operation="t", storage=storage)
    def generate():
        return SimpleNamespace(usage=SimpleNamespace(input_tokens=1, output_tokens=1))

    generate()
    rows = storage.query()
    assert rows[0].cost_usd == 0.0
    assert rows[0].metadata_json.get("pricing_unknown") is True
