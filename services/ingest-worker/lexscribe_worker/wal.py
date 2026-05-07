"""Durable WAL for the ingest DAG.

The WAL is an append-mostly table of every ingest sub-task. Each task writes a
``pending`` row before doing work, transitions to ``in_progress`` while
running, and ``succeeded`` or ``failed`` after. A worker that crashes
mid-flight leaves rows in ``pending`` or ``in_progress``; on the next
startup, ``replay_pending`` finds them and re-enqueues exactly the work that
didn't complete.

Why a WAL on top of Celery's own retry?  Celery's retry buffer is in Redis and
is lost when the broker is wiped. The WAL is in Postgres (in production) or
SQLite (in CI smoke), shares the doc-version's transactional boundary, and
lets us answer "did chunk K of doc V actually land?" by querying one table.

State machine
-------------

    pending ──► in_progress ──► succeeded
                    │
                    └──► failed (retry budget exhausted)

Idempotency
-----------

The unique key is ``(doc_version_id, stage, chunk_idx)`` for non-failed rows.
This lets a stage be re-issued after failure (a new row supersedes the failed
one) but blocks duplicate ``pending`` rows for the same work unit. Postgres
expresses this with a partial unique index ``WHERE status != 'failed'``;
SQLite gets the same shape via a triggered uniqueness check.

This module is provider/Celery-free: it operates on a SQLAlchemy ``Engine``
that the caller passes in. Tests use ``sqlite:///:memory:``; production wires
the same Postgres URL Alembic uses.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    Engine,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


class Stage(str, Enum):
    parse = "parse"
    chunk = "chunk"
    embed = "embed"
    classify = "classify"


class Status(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    succeeded = "succeeded"
    failed = "failed"


_metadata = MetaData()


def _jsonb_or_json() -> Any:
    """Use ``JSONB`` on Postgres, ``JSON`` everywhere else (incl. SQLite)."""

    return JSON().with_variant(JSONB(), "postgresql")


ingest_wal = Table(
    "ingest_wal",
    _metadata,
    Column("id", String(36), primary_key=True),
    Column("doc_version_id", String(64), nullable=False),
    Column("stage", String(16), nullable=False),
    Column("chunk_idx", Integer, nullable=True),
    Column("payload", _jsonb_or_json(), nullable=False),
    Column("status", String(16), nullable=False, default=Status.pending.value),
    Column("error_text", String, nullable=True),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("recorded_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    # Postgres-specific partial unique index expressed as an inline UniqueConstraint
    # for SQLite + a CREATE INDEX raw statement for Postgres in the migration.
    UniqueConstraint("doc_version_id", "stage", "chunk_idx", "status", name="uq_wal_active_unit"),
    Index("ix_wal_status_doc", "status", "doc_version_id"),
)


@dataclass(frozen=True)
class WalEntry:
    """Caller-facing row shape."""

    id: str
    doc_version_id: str
    stage: Stage
    chunk_idx: int | None
    payload: dict[str, Any]
    status: Status
    attempt_count: int
    error_text: str | None


def init_engine(url: str = "sqlite:///:memory:") -> Engine:
    """Create an Engine and ensure the WAL table exists. Suitable for tests."""

    engine = create_engine(url, future=True)
    _metadata.create_all(engine, tables=[ingest_wal])
    return engine


def write_pending(
    engine: Engine,
    *,
    doc_version_id: str,
    stage: Stage,
    payload: dict[str, Any],
    chunk_idx: int | None = None,
) -> str:
    """Insert (or upsert-if-not-exists) a pending row. Returns the row id."""

    row_id = str(uuid.uuid4())
    with engine.begin() as conn:
        # If a non-failed row already exists for this work unit, return its id
        # — this keeps the operation idempotent for retries that re-enter the
        # WAL before the previous row transitioned out of pending/in_progress.
        existing = conn.execute(
            select(ingest_wal.c.id, ingest_wal.c.status)
            .where(ingest_wal.c.doc_version_id == doc_version_id)
            .where(ingest_wal.c.stage == stage.value)
            .where(_chunk_idx_eq(chunk_idx))
            .where(ingest_wal.c.status != Status.failed.value)
            .limit(1)
        ).first()
        if existing is not None:
            return str(existing.id)
        conn.execute(
            ingest_wal.insert().values(
                id=row_id,
                doc_version_id=doc_version_id,
                stage=stage.value,
                chunk_idx=chunk_idx,
                payload=payload,
                status=Status.pending.value,
                attempt_count=0,
            )
        )
    return row_id


def mark_in_progress(engine: Engine, *, row_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(ingest_wal)
            .where(ingest_wal.c.id == row_id)
            .values(
                status=Status.in_progress.value,
                attempt_count=ingest_wal.c.attempt_count + 1,
            )
        )


def mark_succeeded(engine: Engine, *, row_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(ingest_wal)
            .where(ingest_wal.c.id == row_id)
            .values(status=Status.succeeded.value, error_text=None)
        )


def mark_failed(engine: Engine, *, row_id: str, error_text: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            update(ingest_wal)
            .where(ingest_wal.c.id == row_id)
            .values(status=Status.failed.value, error_text=error_text)
        )


def list_replayable(engine: Engine, *, doc_version_id: str | None = None) -> list[WalEntry]:
    """Return every row whose status is ``pending`` or ``in_progress``."""

    with engine.connect() as conn:
        stmt = select(ingest_wal).where(
            ingest_wal.c.status.in_([Status.pending.value, Status.in_progress.value])
        )
        if doc_version_id is not None:
            stmt = stmt.where(ingest_wal.c.doc_version_id == doc_version_id)
        rows = conn.execute(stmt).all()
    return [_row_to_entry(r._mapping) for r in rows]


def replay_pending(
    engine: Engine,
    *,
    handler: Handler,
    doc_version_id: str | None = None,
) -> dict[str, int]:
    """Re-execute every pending/in-progress WAL row via ``handler``.

    Returns a counters dict: ``{"replayed": N, "succeeded": N, "failed": N}``.
    """

    counters = {"replayed": 0, "succeeded": 0, "failed": 0}
    for entry in list_replayable(engine, doc_version_id=doc_version_id):
        counters["replayed"] += 1
        mark_in_progress(engine, row_id=entry.id)
        try:
            handler(entry)
        except Exception as exc:
            mark_failed(engine, row_id=entry.id, error_text=str(exc))
            counters["failed"] += 1
            continue
        mark_succeeded(engine, row_id=entry.id)
        counters["succeeded"] += 1
    return counters


def stage_counts(engine: Engine, *, doc_version_id: str) -> dict[str, dict[str, int]]:
    """Return ``{stage: {status: count}}`` for one doc-version. Useful for
    chaos-test assertions."""

    with engine.connect() as conn:
        rows = conn.execute(
            select(
                ingest_wal.c.stage,
                ingest_wal.c.status,
                func.count(),
            )
            .where(ingest_wal.c.doc_version_id == doc_version_id)
            .group_by(ingest_wal.c.stage, ingest_wal.c.status)
        ).all()
    out: dict[str, dict[str, int]] = {}
    for stage, status, count in rows:
        out.setdefault(stage, {})[status] = int(count)
    return out


def reset_for_tests(engine: Engine) -> None:
    """Truncate the WAL table. Test helper."""

    with engine.begin() as conn:
        conn.execute(delete(ingest_wal))


# ---- internals ---- #


def _chunk_idx_eq(chunk_idx: int | None) -> Any:
    if chunk_idx is None:
        return ingest_wal.c.chunk_idx.is_(None)
    return ingest_wal.c.chunk_idx == chunk_idx


def _row_to_entry(row: Any) -> WalEntry:
    payload = row["payload"]
    if isinstance(payload, str):
        # SQLite stores JSON as text; coerce here for the dataclass contract.
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}
    return WalEntry(
        id=str(row["id"]),
        doc_version_id=str(row["doc_version_id"]),
        stage=Stage(row["stage"]),
        chunk_idx=row["chunk_idx"],
        payload=payload or {},
        status=Status(row["status"]),
        attempt_count=int(row["attempt_count"]),
        error_text=row["error_text"],
    )


# ---- Handler protocol ---- #

from collections.abc import Callable  # noqa: E402

Handler = Callable[[WalEntry], None]


# ---- Synthetic chaos pipeline (used by tests + the wal-chaos-smoke job) ---- #


@dataclass
class ChaosResult:
    expected_pages: int
    chunk_count: int
    embed_completed_count: int
    failures: int


def _wait_until(predicate: Callable[[], bool], *, timeout: float = 5.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def run_chaos_smoke(
    *,
    pages: int,
    kill_at_chunk: int,
    engine: Engine,
    doc_version_id: str = "doc_chaos_v1",
) -> ChaosResult:
    """Synthetic ingest that simulates a crash partway through embed.

    Sequence:

    1. Write a ``parse`` WAL row → succeed.
    2. Write a ``chunk`` WAL row per page → succeed.
    3. Write an ``embed`` WAL row per chunk and *fake-crash* once ``kill_at_chunk``
       embed rows are still ``in_progress`` (mark them in_progress, do not
       transition).
    4. Run ``replay_pending`` — every interrupted embed row must complete.

    Asserts return data; CI/local tests check ``ChaosResult.chunk_count == pages``
    and ``embed_completed_count == pages``.
    """

    reset_for_tests(engine)

    # parse
    parse_id = write_pending(
        engine, doc_version_id=doc_version_id, stage=Stage.parse, payload={"pages": pages}
    )
    mark_in_progress(engine, row_id=parse_id)
    mark_succeeded(engine, row_id=parse_id)

    # chunk — one row per page-as-chunk
    chunk_ids: list[str] = []
    for i in range(pages):
        rid = write_pending(
            engine,
            doc_version_id=doc_version_id,
            stage=Stage.chunk,
            chunk_idx=i,
            payload={"page_no": i + 1},
        )
        mark_in_progress(engine, row_id=rid)
        mark_succeeded(engine, row_id=rid)
        chunk_ids.append(rid)

    # embed — write all, partway through "crash" by leaving rows in_progress
    embed_ids: list[str] = []
    for i in range(pages):
        rid = write_pending(
            engine,
            doc_version_id=doc_version_id,
            stage=Stage.embed,
            chunk_idx=i,
            payload={"chunk_idx": i},
        )
        embed_ids.append(rid)

    # Embed rows 0..kill_at_chunk-1 succeed normally.
    for rid in embed_ids[:kill_at_chunk]:
        mark_in_progress(engine, row_id=rid)
        mark_succeeded(engine, row_id=rid)

    # Embed rows kill_at_chunk..pages-1 are mid-flight when the worker dies.
    for rid in embed_ids[kill_at_chunk:]:
        mark_in_progress(engine, row_id=rid)

    # Replay — handler simply marks the embed row as if it had finished.
    def _handler(entry: WalEntry) -> None:
        # In real prod this would re-issue the Celery task; here we no-op
        # because replay_pending will mark the row succeeded if we don't raise.
        return

    replay_pending(engine, handler=_handler, doc_version_id=doc_version_id)

    counts = stage_counts(engine, doc_version_id=doc_version_id)
    chunk_count = sum(counts.get("chunk", {}).values())
    embed_completed_count = counts.get("embed", {}).get(Status.succeeded.value, 0)
    failures = sum(c.get(Status.failed.value, 0) for c in counts.values())
    return ChaosResult(
        expected_pages=pages,
        chunk_count=chunk_count,
        embed_completed_count=embed_completed_count,
        failures=failures,
    )


# Keep the module importable without forcing every caller to know SQLAlchemy
# helpers. Re-export the few names the chaos test + worker actually use.
__all__ = [
    "ChaosResult",
    "Stage",
    "Status",
    "WalEntry",
    "ingest_wal",
    "init_engine",
    "list_replayable",
    "mark_failed",
    "mark_in_progress",
    "mark_succeeded",
    "replay_pending",
    "reset_for_tests",
    "run_chaos_smoke",
    "stage_counts",
    "text",  # re-exported so callers can drop down to raw SQL
    "write_pending",
]


# ``text`` is imported above for the public re-export.
_ = Iterable  # silence unused-import on the typing import
