"""initial schema: tenants, documents, doc_versions, pages, chunks, spans, risk_flags, failed_jobs.

Revision ID: 0001
Revises:
Create Date: 2026-04-30 00:00:00
"""

from __future__ import annotations

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE tenants (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug         TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TYPE document_status AS ENUM (
            'pending','parsing','embedding','classifying','active','failed'
        )
        """
    )

    op.execute(
        """
        CREATE TABLE documents (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            sha256          CHAR(64) NOT NULL,
            filename        TEXT NOT NULL,
            status          document_status NOT NULL DEFAULT 'pending',
            current_version INT NOT NULL DEFAULT 1,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (tenant_id, sha256)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE doc_versions (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            document_id  UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            version      INT NOT NULL,
            s3_key       TEXT NOT NULL,
            page_count   INT NOT NULL DEFAULT 0,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (document_id, version)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE pages (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            doc_version_id  UUID NOT NULL REFERENCES doc_versions(id) ON DELETE CASCADE,
            page_no         INT NOT NULL,
            text            TEXT NOT NULL,
            ocr_used        BOOLEAN NOT NULL DEFAULT FALSE,
            UNIQUE (doc_version_id, page_no)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE chunks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id     UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            char_start  INT NOT NULL,
            char_end    INT NOT NULL,
            text        TEXT NOT NULL,
            embedding   vector(1536),
            tsv         tsvector GENERATED ALWAYS AS (to_tsvector('english', text)) STORED
        )
        """
    )

    op.execute(
        """
        CREATE TYPE clause_type AS ENUM (
            'change_of_control','ip_assignment','exclusivity','termination',
            'indemnity','governing_law','other'
        )
        """
    )

    op.execute(
        """
        CREATE TABLE spans (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            page_id     UUID NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
            char_start  INT NOT NULL,
            char_end    INT NOT NULL,
            clause_type clause_type NOT NULL,
            confidence  REAL NOT NULL DEFAULT 0.0
        )
        """
    )

    op.execute(
        """
        CREATE TABLE risk_flags (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            span_id      UUID NOT NULL REFERENCES spans(id) ON DELETE CASCADE,
            severity     TEXT NOT NULL,
            description  TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE failed_jobs (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            queue         TEXT NOT NULL,
            stage         TEXT NOT NULL,
            doc_id        UUID,
            doc_version   INT,
            chunk_idx     INT,
            attempts      INT NOT NULL,
            last_error    TEXT NOT NULL,
            payload       JSONB NOT NULL,
            failed_at     TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )

    # Indexes — kept after table creation so the smoke test doesn't time out.
    # In production these should be CREATE INDEX CONCURRENTLY (Alembic supports
    # autocommit_block() for that). The migration here keeps it inline so the
    # full up/down round-trip is one transaction in tests.
    op.execute(
        "CREATE INDEX chunks_embedding_hnsw "
        "ON chunks USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute("CREATE INDEX chunks_tsv_gin ON chunks USING gin (tsv)")
    op.execute(
        "CREATE INDEX documents_active_by_tenant "
        "ON documents (tenant_id) WHERE status = 'active'"
    )
    op.execute("CREATE INDEX failed_jobs_doc ON failed_jobs (doc_id, doc_version)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS failed_jobs")
    op.execute("DROP TABLE IF EXISTS risk_flags")
    op.execute("DROP TABLE IF EXISTS spans")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS pages")
    op.execute("DROP TABLE IF EXISTS doc_versions")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS tenants")
    op.execute("DROP TYPE IF EXISTS clause_type")
    op.execute("DROP TYPE IF EXISTS document_status")
