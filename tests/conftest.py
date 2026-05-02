"""Shared pytest fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# Ensure the workspace packages are importable when ``pip install -e .`` did not
# pick up the namespaces (e.g. when developers run pytest directly).
ROOT = Path(__file__).resolve().parent.parent
for sub in (
    "packages/shared",
    "packages/retrieval",
    "packages/eval",
    "packages/clients/python",
    "services/api",
    "services/ingest-worker",
):
    p = str(ROOT / sub)
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block real provider keys from leaking into tests."""

    monkeypatch.setenv("LEXSCRIBE_ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("LEXSCRIBE_OPENAI_API_KEY", "")
    monkeypatch.setenv("LEXSCRIBE_OTEL_ENABLED", "false")


def _integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION", "").lower() in ("1", "true", "yes")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if _integration_enabled():
        return
    skip_integration = pytest.mark.skip(reason="integration tests require RUN_INTEGRATION=1")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
