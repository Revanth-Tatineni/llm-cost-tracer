# How a traced call actually flows

## 1. Configuring where records go

Before any call is traced, something resolves a `Storage` instance. Most of the time nobody
calls anything explicitly — `tracer.py`'s `_TraceSession.__init__` does
`storage or get_default_storage()`, and `config.get_default_storage()` lazily calls
`configure()` on first use, which reads `LLM_COST_TRACER_DB_URL` from the environment
(defaulting to `sqlite:///llm_cost_tracer.db` if it isn't set). `Storage.__init__` then opens
a SQLAlchemy engine and runs `Base.metadata.create_all(engine)`, so the
`llm_cost_tracer_records` table exists the first time
any process touches it — there's no separate "init" step to remember.

## 2. The decorator path (the common case)

```python
@trace(provider="anthropic", model="claude-opus-5", operation="qa.generate")
def generate(prompt: str):
    return client.messages.create(...)
```

```
trace(...)                 -- called once, at import/definition time, returns `decorator`
  decorator(generate)      -- wraps `generate`, returns `sync_wrapper` (or `async_wrapper`,
                               chosen via inspect.iscoroutinefunction(func))
      |
      v  (every call to generate(...) now actually calls sync_wrapper(...))
with trace_call(provider, model, op, project, storage, fallback_rate) as ctx:
    result = func(*args, **kwargs)        # the real generate() body runs here
    ctx.record_response(result)           # try to pull tokens off `result`
    return result
```

Inside `trace_call(...)`, a `_TraceSession` is created and entered:

```
_TraceSession.__enter__():
    self._start = time.perf_counter()
    self._token = _current_context_var.set(self.context)   # current_trace() now returns this
    return self.context
```

`func(*args, **kwargs)` runs — this is the actual LLM call, completely opaque to the tracer.
When it returns, `ctx.record_response(result)` calls `extract_tokens(provider, result)`, which
dispatches to `extract_anthropic` or `extract_openai` based on the `provider=` string; if that
extractor finds a `usage` object on `result` (or in it, if `result` is a dict), the record's
`input_tokens`/`output_tokens` are set. If nothing matches, they're left at `0` — no error.

## 3. Finishing the call -- success or exception, same path

`with` always calls `__exit__` on the way out, whether the block raised or not:

```
_TraceSession._finish(exc):
    latency_ms = (perf_counter() - start) * 1000
    if exc is not None:
        status = "error"; error = f"{type(exc).__name__}: {exc}"
    try:
        cost_usd = calculate_cost(provider, model, input_tokens, output_tokens, fallback_rate)
    except UnknownPricingError:
        cost_usd = 0.0
        metadata["pricing_unknown"] = True
    storage.save(record)
    _current_context_var.reset(token)     # restores whatever current_trace() returned before
```

`__exit__` returns `None` (not `True`), so a raised exception is **never swallowed** — it
propagates to whoever called `generate(...)`, exactly as if `@trace` weren't there, after the
record has already been saved with `status="error"`. This is the one invariant the whole design
protects: tracing a call must never change whether that call raises.

## 4. The context-manager path (when the decorator doesn't fit)

```python
with trace_call(provider="anthropic", model="claude-opus-5", operation="qa.generate") as t:
    response = client.messages.create(...)
    t.record_response(response)      # same extractor logic, called manually
    t.set_quality(judge_score)       # not available to the decorator form at all
    t.add_metadata(user_id=user.id)
```

Same `_TraceSession` underneath, same `_finish()` on the way out — the only difference is *who*
calls `record_response`/`set_quality`/`add_metadata`: the decorator calls `record_response`
automatically with the function's return value; here, the caller calls whatever subset of
`TraceContext`'s methods applies, at whatever point in the block makes sense (e.g. after parsing
a response into something else, when the raw object would otherwise be lost).

## 5. Reaching the in-flight trace from deeper in the call stack

```python
@trace(provider="anthropic", model="claude-opus-5", operation="qa.generate")
def generate(prompt: str):
    response = client.messages.create(...)
    score = run_judge(response)          # some nested call, several frames deep
    current_trace().set_quality(score)   # reaches back to *this* call's TraceContext
    return response
```

`current_trace()` just reads `_current_context_var.get()`. Because it's a `contextvars.ContextVar`
set via `.set()` inside `__enter__`, any code running underneath that `with` block --
including code called several functions deeper, in the same task -- sees the same context. Two
*concurrent* traced calls (two asyncio tasks, or two threads) each get their own value; neither
sees the other's `current_trace()`. Outside of any traced call, `current_trace()` returns `None`.

## 6. Reading the data back out

- **`llm-cost-tracer report`** → `cli.py`'s `_cmd_report` →
  `get_default_storage().summary(project=...)`
  → one SQL query (`count`, `sum`, `avg` in a single `SELECT`) → printed as plain text.
- **`llm-cost-tracer dashboard`** → `cli.py`'s `_cmd_dashboard` shells out to
  `streamlit run src/llm_cost_tracer/dashboard/app.py`. The dashboard script builds its *own*
  `Storage(db_url)` directly (reading `LLM_COST_TRACER_DB_URL` itself, not going through
  `config.get_default_storage()`) — Streamlit re-runs the whole script top-to-bottom on every
  interaction, so relying on `config.py`'s process-level singleton would reopen or rebuild state
  unpredictably across reruns. `storage.query(...)` pulls the raw rows into a pandas
  `DataFrame` for charting; `storage.summary(...)` powers the four metric tiles at the top.
