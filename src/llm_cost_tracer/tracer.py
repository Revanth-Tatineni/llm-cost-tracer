"""The core of llm_cost_tracer: a decorator and a context manager that both funnel into the same
_TraceSession, so a wrapped call is timed, priced and saved exactly once no matter which form
is used or whether the call raises.
"""

from __future__ import annotations

import contextvars
import functools
import inspect
import time
from collections.abc import Callable
from typing import Any, TypeVar

from llm_cost_tracer.config import get_default_storage
from llm_cost_tracer.extractors import extract_tokens
from llm_cost_tracer.models import TraceRecord
from llm_cost_tracer.pricing import UnknownPricingError, calculate_cost
from llm_cost_tracer.storage import Storage

F = TypeVar("F", bound=Callable[..., Any])


class TraceContext:
    """Handed to the call in flight (as the `with`/`async with` target, or via
    `current_trace()` inside a @trace-decorated function) so it can correct what the tracer
    guessed: set token counts explicitly, attach a quality score, or add metadata."""

    def __init__(self, record: TraceRecord) -> None:
        self._record = record

    def record_response(self, response: Any) -> None:
        """Try the registered extractor for this call's provider against `response`. A
        decorator calls this automatically with the wrapped function's return value."""
        tokens = extract_tokens(self._record.provider, response)
        if tokens is not None:
            self._record.input_tokens, self._record.output_tokens = tokens

    def set_tokens(self, input_tokens: int, output_tokens: int) -> None:
        self._record.input_tokens = input_tokens
        self._record.output_tokens = output_tokens

    def set_quality(self, score: float) -> None:
        self._record.quality_score = score

    def add_metadata(self, **fields: Any) -> None:
        self._record.metadata.update(fields)


# A contextvar, not a plain module global: each asyncio task and each thread gets its own
# value, so two concurrent traced calls (e.g. two FastAPI requests) never see each other's
# TraceContext through current_trace().
_current_context_var: contextvars.ContextVar[TraceContext | None] = contextvars.ContextVar(
    "llm_cost_tracer_current_context", default=None
)


def current_trace() -> TraceContext | None:
    """The TraceContext for the call currently in flight, or None outside of one."""
    return _current_context_var.get()


class _TraceSession:
    """Shared by `trace()` and `trace_call()`: start the clock, run the body, and on the way
    out -- success or exception -- price the call and save exactly one record."""

    def __init__(
        self,
        provider: str,
        model: str,
        operation: str,
        project: str,
        storage: Storage | None,
        fallback_rate: tuple[float, float] | None,
    ) -> None:
        self.record = TraceRecord(
            provider=provider, model=model, operation=operation, project=project
        )
        self.storage = storage or get_default_storage()
        self.fallback_rate = fallback_rate
        self.context = TraceContext(self.record)
        self._start = 0.0
        self._token: contextvars.Token[TraceContext | None] | None = None

    def __enter__(self) -> TraceContext:
        self._start = time.perf_counter()
        self._token = _current_context_var.set(self.context)
        return self.context

    def _finish(self, exc: BaseException | None) -> None:
        self.record.latency_ms = (time.perf_counter() - self._start) * 1000
        if exc is not None:
            self.record.status = "error"
            self.record.error = f"{type(exc).__name__}: {exc}"
        try:
            self.record.cost_usd = calculate_cost(
                self.record.provider,
                self.record.model,
                self.record.input_tokens,
                self.record.output_tokens,
                fallback_rate=self.fallback_rate,
            )
        except UnknownPricingError:
            self.record.cost_usd = 0.0
            self.record.metadata["pricing_unknown"] = True
        self.storage.save(self.record)
        if self._token is not None:
            _current_context_var.reset(self._token)

    def __exit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        self._finish(exc)

    async def __aenter__(self) -> TraceContext:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc: BaseException | None, tb: Any) -> None:
        self._finish(exc)


def trace_call(
    *,
    provider: str,
    model: str,
    operation: str = "llm.call",
    project: str = "default",
    storage: Storage | None = None,
    fallback_rate: tuple[float, float] | None = None,
) -> _TraceSession:
    """Context manager form, for a call that doesn't fit a clean decorator:

        with trace_call(provider="anthropic", model="claude-opus-5", operation="qa.generate") as t:
            response = client.messages.create(...)
            t.record_response(response)
            t.set_quality(0.92)

    Works with `async with` too.
    """
    return _TraceSession(provider, model, operation, project, storage, fallback_rate)


def trace(
    *,
    provider: str,
    model: str,
    operation: str | None = None,
    project: str = "default",
    storage: Storage | None = None,
    fallback_rate: tuple[float, float] | None = None,
) -> Callable[[F], F]:
    """Decorator form. Wraps a sync or async function, times it, and feeds whatever it
    returns to `record_response` so tokens are picked up automatically when the function
    returns the raw SDK response. Call `current_trace()` inside the function to override
    tokens/quality/metadata when it doesn't.

        @trace(provider="anthropic", model="claude-opus-5", operation="qa.generate")
        def generate(prompt: str):
            return client.messages.create(...)
    """

    def decorator(func: F) -> F:
        op = operation or func.__qualname__

        if inspect.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                async with trace_call(
                    provider=provider,
                    model=model,
                    operation=op,
                    project=project,
                    storage=storage,
                    fallback_rate=fallback_rate,
                ) as ctx:
                    result = await func(*args, **kwargs)
                    ctx.record_response(result)
                    return result

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_call(
                provider=provider,
                model=model,
                operation=op,
                project=project,
                storage=storage,
                fallback_rate=fallback_rate,
            ) as ctx:
                result = func(*args, **kwargs)
                ctx.record_response(result)
                return result

        return sync_wrapper  # type: ignore[return-value]

    return decorator
