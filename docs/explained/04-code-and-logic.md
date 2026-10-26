# Code and logic, file by file

This is the grounded walkthrough: real function and class names, real values, from the code as
it actually exists in `src/llmtrace/` right now.

## `models.py`

```python
@dataclass
class TraceRecord:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.time)
    ...
    metadata: dict = field(default_factory=dict)
```

Every mutable-looking default (`id`, `started_at`, `metadata`) uses `field(default_factory=...)`,
never a bare `= {}` or `= uuid.uuid4().hex`. A bare mutable default on a dataclass/function is
evaluated once at class-definition time and shared across every instance — the classic Python
footgun. `default_factory` calls the lambda fresh for each new `TraceRecord`, so two records
never accidentally share one `metadata` dict.

## `pricing.py`

```python
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {"claude-opus-5": (15.0, 75.0), ...},
    ...
}

def calculate_cost(provider, model, input_tokens, output_tokens, *, fallback_rate=None) -> float:
    rates = PRICING.get(provider, {}).get(model)
    if rates is None:
        if fallback_rate is None:
            raise UnknownPricingError(...)
        rates = fallback_rate
    input_rate, output_rate = rates
    return (input_tokens / 1_000_000) * input_rate + (output_tokens / 1_000_000) * output_rate
```

The `*` before `fallback_rate` forces it to be passed by keyword — `calculate_cost("a", "b", 1,
2, (3, 4))` is a `TypeError`, not a silent misread of which tuple means what. `UnknownPricingError`
is declared as `class UnknownPricingError(KeyError)`, which means `except KeyError:` at a call
site would also catch it (it genuinely is a lookup failure), while `except UnknownPricingError:`
lets `tracer.py` catch *only* this specific case without swallowing an unrelated `KeyError` from
somewhere else in the same `try` block. `register_pricing` is one line —
`PRICING.setdefault(provider, {})[model] = (input_rate, output_rate)` — mutating the module-level
dict in place, so a rate registered once (e.g. at the top of a user's app) is visible to every
later `calculate_cost` call in that process.

## `extractors.py`

```python
def _usage_of(response: Any) -> Any:
    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")
    return usage

def _field(usage: Any, attr: str, key: str) -> int | None:
    value = getattr(usage, attr, None)
    if value is None and isinstance(usage, dict):
        value = usage.get(key)
    return value
```

`_usage_of` and `_field` are the two helpers every extractor shares: try attribute access first
(matches a real SDK response object, e.g. Anthropic's `BetaMessage.usage.input_tokens`), fall
back to dict access (matches a plain dict, which is what the test suite builds instead of
installing the Anthropic SDK). `extract_anthropic` and `extract_openai` are then just two calls
to `_field` with different attribute/key names (`input_tokens`/`output_tokens` vs.
`prompt_tokens`/`completion_tokens` — the two SDKs name the same concept differently).
`extract_tokens(provider, response)` is the dispatcher: a dict lookup into `_EXTRACTORS` by
provider string, returning `None` (not raising) for an unregistered provider — `tracer.py` relies
on that `None` meaning "leave tokens at 0," not "something went wrong."

## `storage.py`

```python
class TraceRow(Base):
    __tablename__ = "llmtrace_records"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    ...
```

Uses SQLAlchemy 2.0's `Mapped[...]`/`mapped_column()` style, not the older
`id = Column(String, primary_key=True)` style. This isn't just a style preference: with plain
`Column(...)` attributes, mypy sees the *class* attribute as typed `Column[str]`, not `str` — so
code reading `row.project` (e.g. the dashboard's `{row.project for row in all_rows}`) type-checks
as iterating `Column[str]` objects, not real strings, and fails `mypy src` with a type error.
Switching to `Mapped[str]` was the actual fix applied in this project after `mypy` caught exactly
that error on the dashboard.

```python
def save(self, record: TraceRecord) -> None:
    row = TraceRow(id=record.id, ...)
    with self._session_factory() as session:
        session.merge(row)
        session.commit()
```

`session.merge(row)` is used instead of `session.add(row)`. `add` would raise on a duplicate
primary key; `merge` inserts if the id is new and updates if it already exists. In the current
code every `TraceRecord` gets a fresh `uuid4().hex`, so this path isn't exercised today — it's a
deliberate defensive choice for a future case (a caller retrying a save with the same id) rather
than something the current call sites rely on.

```python
def summary(self, *, project=None) -> dict[str, Any]:
    stmt = select(
        func.count(TraceRow.id),
        func.coalesce(func.sum(TraceRow.cost_usd), 0.0),
        func.coalesce(func.avg(TraceRow.latency_ms), 0.0),
        func.coalesce(func.sum(TraceRow.input_tokens), 0),
        func.coalesce(func.sum(TraceRow.output_tokens), 0),
        func.avg(TraceRow.quality_score),
    )
```

One query computes six aggregates at once, rather than pulling every row into Python and summing
in a loop — the database does the arithmetic. `func.coalesce(..., 0.0)` matters specifically for
an *empty* table: `SUM()`/`AVG()` over zero rows is SQL `NULL`, and `coalesce` turns that into a
real `0.0`/`0` so `float(total_cost)` doesn't crash on `None`. `quality_score`'s average is
deliberately **not** coalesced — a `NULL` average (no call has ever had a quality score set) is
preserved and translated to Python `None`, which the CLI and dashboard both render as "n/a" / "—"
rather than a misleading `0.0` average quality.

## `tracer.py`

```python
_current_context_var: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "llmtrace_current_context", default=None
)
```

Declared once at module level. `_TraceSession.__enter__` calls
`self._token = _current_context_var.set(self.context)` — note it keeps the returned `Token`,
not just the previous value, specifically so `_finish()` can call
`_current_context_var.reset(self._token)`, which is the contextvars-correct way to restore
exactly the prior state (including "there wasn't one"), rather than assigning a value that might
itself be stale if traces are nested or interleaved.

```python
def __exit__(self, exc_type, exc, tb) -> None:
    self._finish(exc)
```

Returns `None`. An earlier version of this method returned `False` explicitly — functionally
identical (both mean "don't suppress the exception"), but `mypy` flagged it: a `__exit__` typed
to return `bool` is read by the type checker as "might return `True`," which would imply this
context manager could swallow exceptions, which it's specifically designed never to do. Typing
it as `-> None` makes the "never suppresses" guarantee visible to the type checker, not just true
by convention.

```python
def trace(*, provider, model, operation=None, ...):
    def decorator(func):
        op = operation or func.__qualname__
        if inspect.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                async with trace_call(...) as ctx:
                    result = await func(*args, **kwargs)
                    ctx.record_response(result)
                    return result
            return async_wrapper
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            with trace_call(...) as ctx:
                result = func(*args, **kwargs)
                ctx.record_response(result)
                return result
        return sync_wrapper
    return decorator
```

`inspect.iscoroutinefunction(func)` picks the wrapper shape *once*, at decoration time (when the
module defining `generate` is imported), not on every call — so there's no per-call branching
cost. `functools.wraps(func)` copies `func.__name__`, `__doc__` and `__qualname__` onto the
wrapper, which is why `op = operation or func.__qualname__` still gets a meaningful default (the
original function's qualified name) even though `func` here is the *un-wrapped* target, read
before wrapping replaces it.

## `cli.py`

```python
def _cmd_dashboard(args):
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    cmd = [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(args.port)]
    return subprocess.call(cmd)
```

Uses `sys.executable -m streamlit` rather than assuming a bare `streamlit` command is on `PATH`
— this matters inside a virtualenv (`uv run llmtrace dashboard`), where `sys.executable` is
guaranteed to be the interpreter that has `streamlit` installed, while a bare `streamlit` on
`PATH` might resolve to a different environment or not exist at all.

## `dashboard/app.py`

```python
cost_by_time = df.set_index("time")["cost_usd"].sort_index().cumsum()
st.line_chart(cost_by_time)
```

`sort_index()` before `cumsum()` matters: `storage.query()` returns rows ordered newest-first
(`ORDER BY started_at DESC`, for the "recent calls" table), but a running cumulative-cost line
needs oldest-to-newest order, or the cumulative sum would visually run backwards.

```python
if df["quality_score"].notna().any():
    st.subheader("Quality score over time")
    ...
```

The quality-score chart only renders at all if at least one row has a non-null score — most
calls, in the current state of the project (nothing feeds `set_quality` yet from a real
integration), won't. Without this guard, the chart would render as an empty, confusing panel on
a fresh install.

## Testing strategy

Like projects 1 and 2, nothing here is tested against a mock database — `tests/conftest.py`'s
`storage` fixture creates a real SQLite file in `tmp_path` per test, and `Storage` talks to it
through the real SQLAlchemy engine. The only things faked are the *LLM response objects*
themselves (`SimpleNamespace(usage=SimpleNamespace(input_tokens=..., output_tokens=...))` in
`test_tracer.py`), because the point of these tests is to verify `llmtrace`'s own logic, not to
exercise a real Anthropic/OpenAI call. `test_tracer.py::test_decorator_records_error_and_reraises`
is the test that directly protects the one invariant `03-flow.md` calls out: a traced function
that raises must still raise, after its error is recorded — the test asserts both halves.
