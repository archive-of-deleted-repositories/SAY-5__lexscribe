"""Add canonical-text content hashes for verifiable citations.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-07 20:00:00

* ``doc_versions.canonical_hash`` — sha256 hex of NFKC + lower + ws-collapse
  of the full doc text. Frozen at ingest.
* ``chunks.chunk_hash``           — sha256 hex of the canonical chunk text.
  Frozen at ingest.

For existing rows the data migration backfills both columns by recomputing
the hash from the row's stored text. This keeps the migration safe to run
on a populated database without re-ingesting.

Both columns are added with ``NOT NULL`` *after* the backfill. Adding the
column nullable, populating, then enforcing NOT NULL is the standard
Postgres-safe sequence for a non-empty table.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


_WS = re.compile(r"\s+")


def _canonicalize(text: str) -> str:
    return _WS.sub(" ", unicodedata.normalize("NFKC", text).lower()).strip()


def _hash(text: str) -> str:
    return hashlib.sha256(_canonicalize(text).encode("utf-8")).hexdigest()


def upgrade() -> None:
    op.execute("ALTER TABLE doc_versions ADD COLUMN canonical_hash TEXT")
    op.execute("ALTER TABLE chunks ADD COLUMN chunk_hash TEXT")

    # Data migration. Use server-side SQL so the backfill is one round-trip
    # per chunk instead of N. We use Postgres' built-in ``digest`` (from
    # pgcrypto, which 0001 already enables) plus the same canonicalisation
    # pipeline expressed as SQL: ``regexp_replace`` collapses whitespace,
    # ``lower`` matches the Python lower(), and ``normalize`` covers NFKC.
    #
    # Note: PostgreSQL ``normalize(text, NFKC)`` is available from 13+.
    op.execute(
        """
        UPDATE chunks
        SET chunk_hash = encode(
            digest(
                trim(
                    regexp_replace(
                        lower(normalize(text, NFKC)),
                        E'\\s+', ' ', 'g'
                    )
                ),
                'sha256'
            ),
            'hex'
        )
        WHERE chunk_hash IS NULL
        """
    )

    # For doc_versions, the canonical text is the concatenation of pages in
    # page_no order. We compute it inline via a CTE.
    op.execute(
        """
        UPDATE doc_versions dv
        SET canonical_hash = sub.h
        FROM (
            SELECT
                p.doc_version_id AS doc_version_id,
                encode(
                    digest(
                        trim(
                            regexp_replace(
                                lower(normalize(string_agg(p.text, E'\\n' ORDER BY p.page_no), NFKC)),
                                E'\\s+', ' ', 'g'
                            )
                        ),
                        'sha256'
                    ),
                    'hex'
                ) AS h
            FROM pages p
            GROUP BY p.doc_version_id
        ) AS sub
        WHERE dv.id = sub.doc_version_id
          AND dv.canonical_hash IS NULL
        """
    )

    # If there are doc_versions with no pages (unlikely outside tests), set
    # the hash to the canonical empty-string digest so NOT NULL holds.
    empty_hash = _hash("")
    op.execute(
        f"UPDATE doc_versions SET canonical_hash = '{empty_hash}' WHERE canonical_hash IS NULL"
    )

    op.execute("ALTER TABLE doc_versions ALTER COLUMN canonical_hash SET NOT NULL")
    op.execute("ALTER TABLE chunks ALTER COLUMN chunk_hash SET NOT NULL")

    op.execute("CREATE INDEX chunks_chunk_hash ON chunks (chunk_hash)")
    op.execute("CREATE INDEX doc_versions_canonical_hash ON doc_versions (canonical_hash)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS doc_versions_canonical_hash")
    op.execute("DROP INDEX IF EXISTS chunks_chunk_hash")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS chunk_hash")
    op.execute("ALTER TABLE doc_versions DROP COLUMN IF EXISTS canonical_hash")
