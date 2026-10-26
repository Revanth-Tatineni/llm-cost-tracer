from __future__ import annotations

from llm_cost_tracer.cli import build_parser


def test_report_command_runs_with_no_data(capsys):
    parser = build_parser()
    args = parser.parse_args(["report"])
    exit_code = args.func(args)
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "calls:" in out


def test_dashboard_command_is_registered():
    parser = build_parser()
    args = parser.parse_args(["dashboard", "--port", "9999"])
    assert args.port == 9999
    assert args.func is not None
