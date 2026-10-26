from __future__ import annotations

from llm_cost_tracer.models import TraceRecord


def test_save_and_query_round_trip(storage):
    record = TraceRecord(provider="anthropic", model="claude-sonnet-5", operation="test.op")
    record.input_tokens = 100
    record.output_tokens = 50
    record.cost_usd = 0.001
    storage.save(record)

    rows = storage.query()
    assert len(rows) == 1
    assert rows[0].id == record.id
    assert rows[0].input_tokens == 100


def test_query_filters_by_project(storage):
    a = TraceRecord(provider="anthropic", model="x", operation="op", project="a")
    b = TraceRecord(provider="anthropic", model="x", operation="op", project="b")
    storage.save(a)
    storage.save(b)

    assert [r.id for r in storage.query(project="a")] == [a.id]


def test_summary_aggregates_cost_and_latency(storage):
    for cost, latency in [(1.0, 100.0), (2.0, 200.0)]:
        record = TraceRecord(provider="p", model="m", operation="op")
        record.cost_usd = cost
        record.latency_ms = latency
        storage.save(record)

    summary = storage.summary()
    assert summary["calls"] == 2
    assert summary["total_cost_usd"] == 3.0
    assert summary["avg_latency_ms"] == 150.0


def test_summary_quality_score_none_when_never_set(storage):
    record = TraceRecord(provider="p", model="m", operation="op")
    storage.save(record)
    assert storage.summary()["avg_quality_score"] is None
