# File structure, and why it's shaped this way

## The tree

```
llm-cost-tracer/
├── pyproject.toml              hatchling build, deps, ruff/mypy/pytest config, [project.scripts]
├── README.md                   recruiter-facing summary
├── .env.example                the one env var (LLM_COST_TRACER_DB_URL) this library reads
├── .gitignore
├── src/llm_cost_tracer/
│   ├── __init__.py             the public API surface -- everything re-exported here
│   ├── models.py               TraceRecord (the in-flight, mutable record)
│   ├── pricing.py              PRICING table, calculate_cost(), register_pricing()
│   ├── extractors.py           extract_anthropic/openai, extract_tokens(), register_extractor()
│   ├── config.py                configure(), get_default_storage() -- the default-storage singleton
│   ├── storage.py              TraceRow (SQLAlchemy mapped class), Storage (save/query/summary)
│   ├── tracer.py               TraceContext, current_trace(), trace(), trace_call(), _TraceSession
│   ├── cli.py                  argparse: `llm-cost-tracer dashboard`, `llm-cost-tracer report`
│   └── dashboard/
│       ├── __init__.py         makes dashboard a real subpackage, included in the built wheel
│       └── app.py              the Streamlit page
├── tests/
│   ├── conftest.py             `storage` fixture + autouse per-test isolated default storage
│   ├── test_pricing.py
│   ├── test_extractors.py
│   ├── test_storage.py
│   ├── test_tracer.py
│   └── test_cli.py
└── .github/workflows/ci.yml    lint -> type-check -> test -> build
```

Note: the importable package is `llm_cost_tracer` (underscore -- a dash isn't a legal Python
identifier), while the distribution name on PyPI and the installed CLI command are both
`llm-cost-tracer` (hyphen, the normal PyPI convention). `pip install llm-cost-tracer` gets you
`import llm_cost_tracer` and the `llm-cost-tracer` command -- three different-looking strings
for the same package, which is standard but worth stating explicitly once.

## Why `src/llm_cost_tracer/`, not a flat `llm_cost_tracer/` at the repo root

A flat layout (`llm_cost_tracer/__init__.py` sitting next to `pyproject.toml`) lets `pytest`
silently import the package straight from the working directory instead of the
actually-installed version — a well-known packaging footgun that can hide a broken build
until someone installs the wheel from PyPI and it doesn't work. The `src/` layout
(`src/llm_cost_tracer/...`, declared in `[tool.hatch.build.targets.wheel]`) forces every
import, including in tests, to go through whatever's actually installed in the environment
(`uv sync` installs this project in editable mode, but still through the packaging metadata,
not a bare path hack).

## Why there's no `controllers/` / `services/` / `repositories/` split

Projects 1 and 2 are layered that way because they have an HTTP boundary (controllers), business
rules with transactions (services), and SQL that needs to be testable independently
(repositories). This project has none of that: there's no HTTP request to route, no multi-step
business transaction, and exactly one table. Splitting `save()`/`query()`/`summary()` into a
separate "repository" file under a "service" file would be layering for its own sake, which
project 1's own conventions explicitly warn against (`CLAUDE.md`'s "no dead code / no premature
abstraction" rule applies here as much as it does there).

Instead, the files are organized by **what each one knows about**, in dependency order:

```
models.py  (the data shape)
    ^
pricing.py, extractors.py   (pure functions -- no I/O, no shared state)
    ^
storage.py   (the one stateful thing: a database connection)
    ^
config.py    (picks which Storage instance is "the" default one)
    ^
tracer.py    (orchestrates all of the above into trace()/trace_call())
    ^
cli.py, dashboard/app.py    (two independent front-ends over the same Storage)
```

Nothing below a given layer imports from above it. `pricing.py` and `extractors.py` don't know
`Storage` exists; `storage.py` doesn't know `tracer.py` exists. `tracer.py` is the only module
that imports from everywhere else, because it's the one place that actually needs all four
pieces (a record shape, a cost, a token-extraction attempt, and somewhere to save the result).

## Why `dashboard/` is a package (with `__init__.py`), not a loose script

`cli.py`'s `dashboard` command needs to find `app.py` reliably regardless of where `pip`
installed the package (a user's site-packages directory, not a path relative to the current
working directory). `Path(__file__).parent / "dashboard" / "app.py"` only works correctly if
`dashboard/` is part of the installed package tree — which requires it to be a real subpackage,
hence the (empty) `__init__.py`.

## Why `tests/` mirrors `src/llm_cost_tracer/` file-for-file

`test_pricing.py` tests `pricing.py`, `test_storage.py` tests `storage.py`, and so on, the same
convention projects 1 and 2 use. The payoff is purely findability: given a change to one source
file, there's exactly one test file to open, no guessing which "feature folder" a test might
have landed in.

## Why `conftest.py`'s autouse fixture exists

Every test gets its own isolated `LLM_COST_TRACER_DB_URL` pointed at a fresh `tmp_path` file,
applied automatically (`@pytest.fixture(autouse=True)`) rather than requested explicitly by
each test. Without it, any test that calls `get_default_storage()` indirectly (e.g. through
`cli.py`'s `report` command) would read or write a real `llm_cost_tracer.db` sitting in
whoever's current working directory — making the test suite's result depend on what's already
on disk. The fixture makes every test run against a database that exists only for that one
test.
