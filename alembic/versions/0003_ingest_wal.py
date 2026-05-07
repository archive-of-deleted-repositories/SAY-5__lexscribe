"""ingest_wal: durable replay log for the ingest DAG.

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-07 20:30:00

* New table ``ingest_wal`` with the state machine
  ``pending → in_progress → succeeded`` (with ``failed`` as the terminal
  side branch when retries are exhausted).
* Partial unique index on ``(doc_version_id, stage, chunk_idx)`` for
  ``status != 'failed'``. Failed rows are kept for forensics; a fresh
  attempt inserts a new active row.
* Plain index on ``(status, doc_version_id)`` for the replay scan on
  worker startup.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TYPE ingest_wal_stage AS ENUM ('parse','chunk','embed','classify')
        """
    )
    op.execute(
        """
        CREATE TYPE ingest_wal_status AS ENUM (
            'pending','in_progress','succeeded','failed'
        )
        """
    )
    op.execute(
        """
        CREATE TABLE ingest_wal (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_version_id  UUID NOT NULL REFERENCES doc_versions(id) ON DELETE CASCADE,
            stage           ingest_wal_stage NOT NULL,
            chunk_idx       INT,
            payload         JSONB NOT NULL,
            status          ingest_wal_status NOT NULL DEFAULT 'pending',
            error_text      TEXT,
            attempt_count   INT NOT NULL DEFAULT 0,
            recorded_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    # The partial unique index is the dedup boundary: only one *active* row
    # per work unit. ``COALESCE(chunk_idx, -1)`` lets stage-level rows
    # (chunk_idx IS NULL) participate in the same uniqueness contract as
    # per-chunk rows without two NULLs colliding.
    op.execute(
        """
        CREATE UNIQUE INDEX ingest_wal_active_unit
        ON ingest_wal (doc_version_id, stage, COALESCE(chunk_idx, -1))
        WHERE status != 'failed'
        """
    )
    op.execute(
        "CREATE INDEX ingest_wal_replay_scan ON ingest_wal (status, doc_version_id) "
        "WHERE status IN ('pending','in_progress')"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ingest_wal_replay_scan")
    op.execute("DROP INDEX IF EXISTS ingest_wal_active_unit")
    op.execute("DROP TABLE IF EXISTS ingest_wal")
    op.execute("DROP TYPE IF EXISTS ingest_wal_status")
    op.execute("DROP TYPE IF EXISTS ingest_wal_stage")
