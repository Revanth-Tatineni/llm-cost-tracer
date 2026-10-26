"""`llm-cost-tracer` console entry point: launch the dashboard, or print a one-shot text
summary (for a CI log or a cron job that doesn't want a browser)."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from llm_cost_tracer.config import get_default_storage


def _cmd_dashboard(args: argparse.Namespace) -> int:
    app_path = Path(__file__).parent / "dashboard" / "app.py"
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(app_path),
        "--server.port",
        str(args.port),
    ]
    return subprocess.call(cmd)


def _cmd_report(args: argparse.Namespace) -> int:
    storage = get_default_storage()
    summary = storage.summary(project=args.project)
    print(f"calls:            {summary['calls']}")
    print(f"total cost (USD): {summary['total_cost_usd']:.4f}")
    print(f"avg latency (ms): {summary['avg_latency_ms']:.1f}")
    print(f"input tokens:     {summary['input_tokens']}")
    print(f"output tokens:    {summary['output_tokens']}")
    avg_q = summary["avg_quality_score"]
    print(f"avg quality:      {avg_q:.3f}" if avg_q is not None else "avg quality:      n/a")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="llm-cost-tracer")
    sub = parser.add_subparsers(dest="command", required=True)

    dashboard = sub.add_parser("dashboard", help="Launch the Streamlit dashboard")
    dashboard.add_argument("--port", type=int, default=8501)
    dashboard.set_defaults(func=_cmd_dashboard)

    report = sub.add_parser("report", help="Print a one-shot text summary")
    report.add_argument("--project", default=None)
    report.set_defaults(func=_cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
