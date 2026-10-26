# Architecture decisions, and the alternatives that were rejected

Projects 1 and 2 are layered web services (`controllers → services → repositories`). This
project has almost none of that layering, on purpose — there's no HTTP boundary, no per-request
lifecycle, and no multi-tenant data to isolate. The decisions below are about something
different: how to make a library that's safe to drop into someone else's running process
(including a concurrent, async one) without that process having to think about it.

## Storage: one SQLAlchemy schema, SQLite or Postgres, not two backends

**Chosen:** a single `Storage` class backed by SQLAlchemy Core/ORM, pointed at whatever URL
`LLM_COST_TRACER_DB_URL` gives it. SQLite by default; a Postgres URL works identically.

**Rejected:** writing a `SQLiteStorage` and a separate `PostgresStorage` with a shared
interface (the way the plan's "SQLite/Postgres" phrasing might suggest).

**Why:** SQLAlchemy already abstracts the dialect difference; writing two backend classes would
mean maintaining two copies of the same four methods (`save`, `query`, `summary`) for no real
behavioral difference. The actual risk with "one database, many write paths" (projects 1/2's
multi-tenant Postgres, under real concurrent load) doesn't apply here — this is typically one
process's local trace log, so a single straightforward implementation is correct, not a
shortcut.

## No Alembic, no migrations

Projects 1 and 2 both use Alembic because their schemas evolve under active development with
real user data to preserve. This library ships one stable table (`llm_cost_tracer_records`) and
`Storage.__init__` just calls `Base.metadata.create_all(engine)` — if the schema changes in a
future version, that's a new package version, not a migration someone has to run against their
trace history (which is disposable observability data, not a system of record).

## `contextvars.ContextVar`, not a plain module global or `threading.local`

**Chosen:** `current_trace()` reads from a `contextvars.ContextVar`, set via `.set()`/`.reset()`
with the returned token (see `tracer.py`'s `_TraceSession`).

**Rejected:** a plain `_current_context` module-level global variable, and `threading.local`.

**Why:** this library's whole value proposition is being safe to drop into someone else's
running service — and that service might be `rag-qa-api`, an **async** FastAPI app handling
concurrent requests. A plain module global would let two requests traced at the same time stomp
on each other's "current" context. `threading.local` doesn't fix this under asyncio, because
many concurrent coroutines typically run on the *same* OS thread — they'd still share one
`threading.local` value. `contextvars.ContextVar` is the one primitive Python gives you that is
correctly isolated per `asyncio.Task` *and* per thread, which is exactly the concurrency model
projects 1/2 actually run under.

## Decorator *and* context manager, not just one

**Chosen:** `trace()` (decorator) and `trace_call()` (context manager) both exist, sharing one
internal `_TraceSession` implementation.

**Why both:** the decorator covers the common case — a function that calls an LLM and returns
the SDK's raw response object, so tokens can be auto-extracted from the return value. But
`rag-qa-api`'s actual `ClaudeAnswerGenerator.generate` doesn't return the raw `BetaMessage` — it
parses it into the service's own result type. A decorator alone can't see the intermediate
response in that case. The context manager form exists for exactly that: call
`t.record_response(raw_response)` manually at the point where the raw object is still in scope,
before it gets parsed away.

## Duck-typed extractors, no required LLM SDK dependency

**Chosen:** `extractors.py` reads `response.usage.input_tokens` (or, if that attribute doesn't
exist, `response["usage"]["input_tokens"]`) without importing `anthropic` or `openai`.

**Rejected:** importing the Anthropic/OpenAI SDK types and doing `isinstance` checks against
them.

**Why:** that would force every `llm-cost-tracer` user to have the Anthropic and/or OpenAI SDK
installed as a transitive dependency, even if they only use one of them (or neither — a custom
or local model). `pyproject.toml`'s only required dependency is `sqlalchemy`. The cost is that
extraction is best-effort (a typo'd attribute name just returns `None` silently rather than
raising); that trade-off is deliberate, since a monitoring library crashing the call it's
monitoring would be a much worse failure mode than under-reporting tokens for one call.

## Pricing as a mutable table with an explicit escape hatch, not a hardcoded formula

**Chosen:** `pricing.py`'s `PRICING` dict, `register_pricing()` to add/override a rate at
runtime, and `fallback_rate=` as a per-call override when a model isn't in the table yet.
`UnknownPricingError` subclasses `KeyError` (so it's catchable either specifically or generically)
and `PRICING_LAST_UPDATED` is a plain string constant, not machine-enforced — it's a note to
the maintainer, not a validation.

**Why:** LLM pricing changes faster than library release cycles. A hardcoded cost formula would
be silently wrong within months. `tracer.py` itself treats an unknown model as "cost 0.0, flag it
in metadata" rather than crashing the traced call — see `04-code-and-logic.md` for exactly where.

## `dataclass`, not Pydantic, for `TraceRecord`

**Chosen:** `TraceRecord` is a plain `@dataclass`.

**Why not Pydantic (used throughout projects 1/2):** Pydantic earns its cost in projects 1/2
because their models sit at an HTTP boundary — untrusted JSON has to be validated and coerced.
`TraceRecord` never crosses a validation boundary; it's an in-process, in-flight mutable
container that `_TraceSession` fills in as the call progresses, then hands to `Storage.save()`.
Adding Pydantic here would be a dependency for a feature (input validation) this object never
needs.

## Streamlit, not a custom FastAPI+React dashboard

The plan explicitly allowed either ("Streamlit or small FastAPI+React"). Streamlit won because
the actual requirement — a handful of charts and a table over one SQL table, refreshed on
page load — doesn't need a custom API layer, and this project's time budget (about a week,
per the plan) goes further building the tracing library itself than building a second web
frontend. `cli.py`'s `dashboard` subcommand shells out to `streamlit run` via `subprocess.call`
rather than importing Streamlit as a library, because Streamlit's execution model expects to
run a `.py` file as a script, not be driven as an importable API.

## `argparse`, not `click`/`typer`

The CLI (`dashboard`, `report`) is two subcommands with a handful of flags — exactly what
`argparse` (stdlib, zero extra dependency) handles without friction. Adding `click` or `typer`
would be a dependency purely for a CLI this small, undercutting the "lightweight" pitch in the
README.
