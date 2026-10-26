"""llm_cost_tracer -- lightweight cost, latency and quality tracing for LLM calls.

    from llm_cost_tracer import trace

    @trace(provider="anthropic", model="claude-opus-5", operation="qa.generate")
    def generate(prompt: str):
        return client.messages.create(...)

Every call is timed, priced from the built-in pricing table, and saved to a local SQLite
file (or Postgres, via LLM_COST_TRACER_DB_URL). `llm-cost-tracer dashboard` opens a Streamlit
view over it.
"""

from llm_cost_tracer.config import configure, get_default_storage
from llm_cost_tracer.models import TraceRecord
from llm_cost_tracer.pricing import calculate_cost, register_pricing
from llm_cost_tracer.storage import Storage
from llm_cost_tracer.tracer import TraceContext, current_trace, trace, trace_call

__all__ = [
    "trace",
    "trace_call",
    "TraceContext",
    "current_trace",
    "TraceRecord",
    "Storage",
    "configure",
    "get_default_storage",
    "calculate_cost",
    "register_pricing",
]

__version__ = "0.1.0"
