from __future__ import annotations

import pytest

from llm_cost_tracer import configure
from llm_cost_tracer.storage import Storage


@pytest.fixture
def storage(tmp_path) -> Storage:
    db_path = tmp_path / "test.db"
    return Storage(f"sqlite:///{db_path}")


@pytest.fixture(autouse=True)
def _isolated_default_storage(tmp_path, monkeypatch):
    """Every test gets its own default-storage file, so tests never share state or touch a
    real llm_cost_tracer.db sitting in the working directory."""
    db_path = tmp_path / "default.db"
    monkeypatch.setenv("LLM_COST_TRACER_DB_URL", f"sqlite:///{db_path}")
    configure()
    yield
