"""Chaos test for the ingest WAL.

Spawns the synthetic 200-page chaos pipeline, simulates a mid-embed crash by
leaving a band of embed rows in ``in_progress`` without a terminal mark, then
invokes ``replay_pending``. After replay, every chunk must have an embed row
in ``succeeded``.

The test is gated on ``RUN_CHAOS=1`` per the v4 spec — at full scale it
exercises 200 pages * 4 stages = 800 WAL rows, which is overkill for the
``wal-chaos-smoke`` CI job. CI runs the smaller-scale test in
``tests/unit/test_wal.py::test_chaos_smoke_recovers_all_pages``.

Run locally with::

    RUN_CHAOS=1 pytest tests/test_wal_chaos.py -v
"""

from __future__ import annotations

import os

import pytest
from lexscribe_worker.wal import init_engine, run_chaos_smoke

_CHAOS_ENABLED = os.environ.get("RUN_CHAOS", "").lower() in ("1", "true", "yes")


@pytest.mark.skipif(not _CHAOS_ENABLED, reason="chaos test gated on RUN_CHAOS=1")
def test_full_scale_chaos_recovers_200_pages() -> None:
    engine = init_engine()
    try:
        result = run_chaos_smoke(pages=200, kill_at_chunk=120, engine=engine)
        # Spec contract:
        assert result.chunk_count == result.expected_pages
        assert result.embed_completed_count == result.chunk_count
        assert result.failures == 0
    finally:
        engine.dispose()
