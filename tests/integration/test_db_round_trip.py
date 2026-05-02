"""Integration smoke: alembic up + down on a real Postgres.

Skipped unless ``RUN_INTEGRATION=1`` and ``LEXSCRIBE_DATABASE_URL`` points at a
reachable pgvector-enabled Postgres.
"""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def test_alembic_up_then_down() -> None:
    pytest.importorskip("alembic")
    from alembic import command
    from alembic.config import Config

    if not os.environ.get("LEXSCRIBE_DATABASE_URL"):
        pytest.skip("LEXSCRIBE_DATABASE_URL not set")

    cfg = Config("alembic.ini")
    command.upgrade(cfg, "head")
    command.downgrade(cfg, "base")
