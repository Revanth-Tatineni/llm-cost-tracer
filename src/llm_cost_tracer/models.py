"""The one record type llm_cost_tracer deals in: one wrapped call, start to finish."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class TraceRecord:
    """One recorded LLM call. Built up during the call (tracer.py) and persisted once at
    the end -- fields default to "nothing happened yet" so a call that errors before any
    tokens are known still saves a usable row."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.time)
    latency_ms: float = 0.0
    provider: str = "unknown"
    model: str = "unknown"
    operation: str = "unknown"
    project: str = "default"
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    quality_score: float | None = None
    status: str = "ok"
    error: str | None = None
    metadata: dict = field(default_factory=dict)
