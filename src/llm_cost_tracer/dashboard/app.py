"""The llm-cost-tracer dashboard. Run it with `llm-cost-tracer dashboard`, or directly:
`streamlit run src/llm_cost_tracer/dashboard/app.py`.
"""

from __future__ import annotations

import os

import pandas as pd
import streamlit as st

from llm_cost_tracer.storage import Storage

st.set_page_config(page_title="llm-cost-tracer", page_icon="📊", layout="wide")

db_url = os.environ.get("LLM_COST_TRACER_DB_URL", "sqlite:///llm_cost_tracer.db")
storage = Storage(db_url)

st.title("llm-cost-tracer")
st.caption(f"Reading from `{db_url}`")

all_rows = storage.query(limit=5000)
projects = sorted({row.project for row in all_rows}) or ["default"]
project = st.sidebar.selectbox("Project", ["(all)"] + projects)
selected_project = None if project == "(all)" else project

summary = storage.summary(project=selected_project)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Calls", summary["calls"])
col2.metric("Total cost", f"${summary['total_cost_usd']:.4f}")
col3.metric("Avg latency", f"{summary['avg_latency_ms']:.0f} ms")
avg_q = summary["avg_quality_score"]
col4.metric("Avg quality", f"{avg_q:.2f}" if avg_q is not None else "—")

rows = storage.query(project=selected_project, limit=2000)
if not rows:
    st.info("No calls recorded yet. Wrap a call with @trace or trace_call(...) first.")
    st.stop()

df = pd.DataFrame(
    [
        {
            "time": r.started_at,
            "provider": r.provider,
            "model": r.model,
            "operation": r.operation,
            "project": r.project,
            "input_tokens": r.input_tokens,
            "output_tokens": r.output_tokens,
            "cost_usd": r.cost_usd,
            "latency_ms": r.latency_ms,
            "quality_score": r.quality_score,
            "status": r.status,
        }
        for r in rows
    ]
)

st.subheader("Cumulative cost")
cost_by_time = df.set_index("time")["cost_usd"].sort_index().cumsum()
st.line_chart(cost_by_time)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Cost by model")
    st.bar_chart(df.groupby("model")["cost_usd"].sum())
with c2:
    st.subheader("Latency by call (ms)")
    st.bar_chart(df.set_index("time")["latency_ms"].sort_index())

if df["quality_score"].notna().any():
    st.subheader("Quality score over time")
    st.line_chart(df.set_index("time")["quality_score"].dropna().sort_index())

st.subheader("Recent calls")
st.dataframe(
    df.sort_values("time", ascending=False)[
        [
            "time",
            "project",
            "provider",
            "model",
            "operation",
            "input_tokens",
            "output_tokens",
            "cost_usd",
            "latency_ms",
            "quality_score",
            "status",
        ]
    ],
    use_container_width=True,
)
