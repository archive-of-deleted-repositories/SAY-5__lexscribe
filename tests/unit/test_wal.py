"""Unit tests for ``lexscribe_worker.wal``.

Uses ``sqlite:///:memory:`` to keep CI hermetic. The same SQLAlchemy code
runs against Postgres in production via the migration in
``alembic/versions/0003_ingest_wal.py``.
"""

from __future__ import annotations

import pytest
from lexscribe_worker.wal import (
    Stage,
    Status,
    init_engine,
    list_replayable,
    mark_failed,
    mark_in_progress,
    mark_succeeded,
    replay_pending,
    reset_for_tests,
    run_chaos_smoke,
    stage_counts,
    write_pending,
)


@pytest.fixture()
def engine():  # type: ignore[no-untyped-def]
    e = init_engine()
    yield e
    e.dispose()


def test_write_pending_creates_one_row(engine) -> None:  # type: ignore[no-untyped-def]
    rid = write_pending(
        engine,
        doc_version_id="doc_a_v1",
        stage=Stage.parse,
        payload={"k": 1},
    )
    assert isinstance(rid, str) and rid
    rows = list_replayable(engine)
    assert len(rows) == 1
    assert rows[0].stage is Stage.parse
    assert rows[0].status is Status.pending
    assert rows[0].payload == {"k": 1}


def test_state_machine_progression(engine) -> None:  # type: ignore[no-untyped-def]
    rid = write_pending(engine, doc_version_id="doc_b_v1", stage=Stage.embed, payload={})
    mark_in_progress(engine, row_id=rid)
    rows = list_replayable(engine)
    assert rows and rows[0].status is Status.in_progress
    assert rows[0].attempt_count == 1
    mark_succeeded(engine, row_id=rid)
    assert list_replayable(engine) == []  # succeeded rows not replayable


def test_failed_rows_are_not_replayable(engine) -> None:  # type: ignore[no-untyped-def]
    rid = write_pending(engine, doc_version_id="doc_c_v1", stage=Stage.classify, payload={})
    mark_in_progress(engine, row_id=rid)
    mark_failed(engine, row_id=rid, error_text="boom")
    assert list_replayable(engine) == []


def test_write_pending_is_idempotent_for_active_rows(engine) -> None:  # type: ignore[no-untyped-def]
    rid1 = write_pending(
        engine, doc_version_id="doc_d_v1", stage=Stage.embed, chunk_idx=7, payload={"a": 1}
    )
    rid2 = write_pending(
        engine, doc_version_id="doc_d_v1", stage=Stage.embed, chunk_idx=7, payload={"a": 2}
    )
    assert rid1 == rid2  # same row returned, payload from first write retained
    rows = list_replayable(engine)
    assert len(rows) == 1


def test_write_pending_after_failure_creates_new_row(engine) -> None:  # type: ignore[no-untyped-def]
    rid1 = write_pending(
        engine, doc_version_id="doc_e_v1", stage=Stage.embed, chunk_idx=2, payload={}
    )
    mark_in_progress(engine, row_id=rid1)
    mark_failed(engine, row_id=rid1, error_text="x")
    rid2 = write_pending(
        engine, doc_version_id="doc_e_v1", stage=Stage.embed, chunk_idx=2, payload={}
    )
    assert rid1 != rid2


def test_replay_pending_marks_succeeded(engine) -> None:  # type: ignore[no-untyped-def]
    write_pending(engine, doc_version_id="doc_f_v1", stage=Stage.parse, payload={})
    counters = replay_pending(engine, handler=lambda _: None)
    assert counters["replayed"] == 1
    assert counters["succeeded"] == 1
    assert counters["failed"] == 0
    assert list_replayable(engine) == []


def test_replay_pending_records_handler_failure(engine) -> None:  # type: ignore[no-untyped-def]
    write_pending(engine, doc_version_id="doc_g_v1", stage=Stage.parse, payload={})

    def boom(_):  # type: ignore[no-untyped-def]
        raise RuntimeError("permanent")

    counters = replay_pending(engine, handler=boom)
    assert counters["failed"] == 1
    # Failed rows aren't replayable
    assert list_replayable(engine) == []


def test_stage_counts_groups_correctly(engine) -> None:  # type: ignore[no-untyped-def]
    for i in range(3):
        rid = write_pending(
            engine, doc_version_id="doc_h_v1", stage=Stage.chunk, chunk_idx=i, payload={}
        )
        mark_in_progress(engine, row_id=rid)
        mark_succeeded(engine, row_id=rid)
    counts = stage_counts(engine, doc_version_id="doc_h_v1")
    assert counts["chunk"]["succeeded"] == 3


def test_reset_for_tests_clears_table(engine) -> None:  # type: ignore[no-untyped-def]
    write_pending(engine, doc_version_id="doc_i_v1", stage=Stage.parse, payload={})
    reset_for_tests(engine)
    assert list_replayable(engine) == []


# ---- Chaos smoke ---- #


def test_chaos_smoke_recovers_all_pages(engine) -> None:  # type: ignore[no-untyped-def]
    result = run_chaos_smoke(pages=10, kill_at_chunk=4, engine=engine)
    assert result.expected_pages == 10
    assert result.chunk_count == 10
    assert result.embed_completed_count == 10
    assert result.failures == 0


def test_chaos_smoke_at_200_pages_passes_recovery_contract(engine) -> None:  # type: ignore[no-untyped-def]
    result = run_chaos_smoke(pages=200, kill_at_chunk=120, engine=engine)
    assert result.chunk_count == 200
    assert result.embed_completed_count == 200
    assert result.failures == 0


def test_chaos_smoke_with_kill_at_zero_still_recovers(engine) -> None:  # type: ignore[no-untyped-def]
    """Edge case: 'crash' before any embed succeeds. Replay must still work."""

    result = run_chaos_smoke(pages=20, kill_at_chunk=0, engine=engine)
    assert result.embed_completed_count == 20


def test_chaos_smoke_with_kill_after_all_does_nothing_to_replay(  # type: ignore[no-untyped-def]
    engine,
) -> None:
    """Edge case: 'crash' after every chunk landed. Replay is a no-op."""

    result = run_chaos_smoke(pages=20, kill_at_chunk=20, engine=engine)
    assert result.embed_completed_count == 20
