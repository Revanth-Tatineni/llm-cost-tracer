"""The default Storage every @trace / trace_call() uses when it isn't given one explicitly.
Most callers never touch this directly -- it's here so a whole process (or a whole test run,
via the `storage` fixture's env var) can point at one database with a single call.
"""

from __future__ import annotations

import os

from llm_cost_tracer.storage import Storage

_default_storage: Storage | None = None


def configure(url: str | None = None) -> Storage:
    """(Re)create the default storage. Reads LLM_COST_TRACER_DB_URL if `url` isn't given, else
    falls back to a local sqlite file. Safe to call again later to point at a different
    database."""
    global _default_storage
    resolved = url or os.environ.get("LLM_COST_TRACER_DB_URL", "sqlite:///llm_cost_tracer.db")
    _default_storage = Storage(resolved)
    return _default_storage


def get_default_storage() -> Storage:
    global _default_storage
    if _default_storage is None:
        _default_storage = configure()
    return _default_storage
