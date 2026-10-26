# llm-cost-tracer

[![CI](https://github.com/Revanth-Tatineni/llm-cost-tracer/actions/workflows/ci.yml/badge.svg)](https://github.com/Revanth-Tatineni/llm-cost-tracer/actions/workflows/ci.yml)

Wrap an LLM call, get its cost, latency and (optionally) a quality score logged automatically.
No agent to run, no SaaS account, no new API key — one decorator, a local SQLite file, and a
Streamlit dashboard.

```python
from llm_cost_tracer import trace


@trace(provider="anthropic", model="claude-opus-5", operation="qa.generate")
def generate(prompt: str):
    return client.messages.create(model="claude-opus-5", messages=[...])
```

Every call through `generate` now has its latency timed, its input/output tokens pulled off
the response automatically, its cost priced from a built-in per-model table, and the record
saved to `llm_cost_tracer.db` (or Postgres, via `LLM_COST_TRACER_DB_URL`) — without touching
the function body.

```bash
pip install llm-cost-tracer              # or: pip install "llm-cost-tracer[dashboard]"
llm-cost-tracer dashboard                 # cost, latency and quality charts — http://localhost:8501
llm-cost-tracer report                    # one-shot text summary, for a CI log or a cron job
```

## Why this exists

Project 3 of a 5-project portfolio. Projects 1 and 2 (a backend API and a RAG Q&A service) both
make real LLM calls and had no visibility into what those calls cost or how slow they were
getting beyond reading a cloud bill after the fact. `rag-qa-api`'s answer generator is the
intended first integration — wrapping `ClaudeAnswerGenerator.generate` with `@trace` is a few
lines once this package is published — but that wiring hasn't been done yet; this package is
tested standalone so far.

## What it tracks

- **Cost** — from a built-in `$/1M tokens` table per provider/model (`register_pricing` to add
  a missing one, or pass `fallback_rate=` per call).
- **Latency** — wall-clock time around the wrapped call.
- **Tokens** — auto-extracted from Anthropic and OpenAI response objects; `register_extractor`
  for another SDK.
- **Quality** — optional: call `current_trace().set_quality(score)` inside the wrapped function
  (e.g. from your own LLM-judge eval) and it's saved alongside the call.
- **Status/errors** — a raised exception is still recorded (`status="error"`) and re-raised
  unchanged, instead of silently losing the trace.

## Two ways to wrap a call

```python
from llm_cost_tracer import current_trace, trace, trace_call


# Decorator — wraps the whole function, auto-extracts tokens from its return value
@trace(provider="anthropic", model="claude-opus-5", operation="qa.generate")
def generate(prompt: str):
    return client.messages.create(...)


# Context manager — for code that doesn't return the raw SDK response, or needs to set
# quality/metadata explicitly
with trace_call(provider="anthropic", model="claude-opus-5", operation="qa.generate") as t:
    response = client.messages.create(...)
    t.record_response(response)
    t.set_quality(judge_score)
    t.add_metadata(user_id=user.id)
```

Both work with `async def` functions and `async with`.

## Storage

SQLite by default (`sqlite:///llm_cost_tracer.db`, created on first use). Point
`LLM_COST_TRACER_DB_URL` (or `configure(url=...)`) at a Postgres URL and the same schema
applies — the dashboard and `llm-cost-tracer report` don't need to know which one is behind it.

## Stack

Python, SQLAlchemy 2 (SQLite/Postgres), Streamlit + pandas for the dashboard, pytest, ruff,
mypy, GitHub Actions. No required dependency on any LLM SDK — it reads whatever response object
you hand it.

## Development

```bash
uv sync --extra dev --extra dashboard
uv run pytest --cov=llm_cost_tracer
uv run ruff check . && uv run mypy src
```

## What I'd add next

- A built-in LLM-as-judge quality scorer, instead of requiring the caller to compute one.
- A budget/alert hook (`on_threshold_exceeded=`) for per-project cost ceilings.
- Batched async-safe writes, so a high-throughput service isn't doing one SQLite write per call.
