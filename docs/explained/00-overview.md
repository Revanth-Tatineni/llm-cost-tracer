# What this project is, and why it exists

## In one paragraph

`llm-cost-tracer` is a small, pip-installable Python library that wraps an LLM API call — one
decorator or one `with` block — and automatically records its latency, its input/output
tokens, its dollar cost, and (optionally) a quality score, into a local SQLite file or a shared
Postgres database. A Streamlit dashboard and a one-shot CLI report sit on top of the same
storage. Nothing about it requires signing up for a SaaS observability product or running an
agent process; it's a library you import, not a service you deploy.

## Where it sits in the bigger plan

This is **project 3 of 5** in the open-source portfolio plan
(`D:\personal\job_applie\projects\open-source-project-plan.md`). It comes after project 1 (the
Knowledge Base API) and project 2 (the RAG Q&A API) on purpose, for a reason that's about
narrative honesty, not difficulty — this is actually the shortest of the three to build:

- **It's explicitly on the target skills list** — "LLMOps" and "Machine Learning Operations"
  are named skills in `applications/applicant-profile.md`, and this is the direct proof point
  for them.
- **It only becomes a believable project once there's something real to monitor.** The plan's
  own words: *"I built this because I needed to track LLM spend across my other projects" is a
  true story only if those other projects already exist."* Building it before project 1/2 existed
  would have made it a toy instrumenting nothing.
- **Publishing it to PyPI and then actually using it inside projects 1/2 turns three separate
  repos into one coherent portfolio narrative** instead of three unrelated one-offs — but that
  narrative only works in this order, and only once the integration actually happens (see
  "Honest current status" below).

## Why a library + PyPI package, not another web service

Projects 1 and 2 are REST APIs: the differentiator is "I can build a production backend."
Project 3 deliberately isn't another FastAPI service — the differentiator here is **"I can ship
something other people `pip install`,"** which is a different and rarer signal at 0-2 years of
experience than another working API. That's why the whole design optimizes for *zero-friction
adoption*: no required database setup (SQLite works immediately), no required LLM SDK dependency
(see `01-architecture.md`), and a one-line decorator rather than a client you have to configure
and instantiate.

## What it concretely does

- `@trace(provider=..., model=..., operation=...)` wraps a function (sync or async), times it,
  and tries to read token usage straight off whatever it returns.
- `trace_call(...)` is the same thing as a context manager, for code that doesn't return the raw
  SDK response or needs to set a quality score explicitly.
- `current_trace()` lets code *inside* a traced call reach back and set a quality score or extra
  metadata — e.g. feeding in a score from your own LLM-as-judge eval, the way `rag-qa-api`'s
  answer eval (`evals/run_answers.py`) could, once wired up.
- Every call is priced from a built-in `$/1M tokens` table, timed, and saved as one row.
- `llm-cost-tracer dashboard` (Streamlit) and `llm-cost-tracer report` (plain text) both read
  that same table.

## Who it's for

- **A recruiter or hiring manager** skimming the GitHub README: a short usage example, a real
  PyPI badge, and a dashboard screenshot, all legible in under a minute.
- **An interviewer** probing LLMOps/observability depth: this `docs/explained/` folder is where
  the actual design reasoning lives — why `contextvars` instead of a plain global, why
  SQLAlchemy instead of two separate storage backends, why pricing is a mutable table instead of
  a hardcoded constant.
- **Future Revanth**, picking this back up before an interview: start at `01-architecture.md`.

## Honest current status (as of this write-up)

- The code is complete and tested: 24 tests pass, `ruff check`/`ruff format --check` and
  `mypy src` are all clean, and the package was smoke-tested end to end in this session — real
  traced calls were recorded, `llm-cost-tracer report` printed correct aggregates, and the Streamlit
  dashboard was launched headless and returned a real HTTP 200.
- **Not yet done:** no git commit, no push to GitHub, no publish to PyPI, no deployment.
- **Not yet true, and corrected in the README during this write-up:** the README originally
  claimed `rag-qa-api`'s `ClaudeAnswerGenerator.generate` was already wrapped with `@trace`. It
  isn't — that integration has not been written. The README now describes it as the *intended*
  first integration instead of an already-done one. Don't claim it on a resume or in an
  interview until the wiring actually exists in `rag-qa-api`.
- The resume line from the plan ("Published an open-source LLM cost/latency/quality monitoring
  library to PyPI, used across my own GenAI projects") is not yet earned on either half: not
  published, and not yet used by another project.
