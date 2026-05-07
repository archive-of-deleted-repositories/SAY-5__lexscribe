"""Worker CLI — DLQ replay, queue depth, WAL replay, etc."""

from __future__ import annotations

import json
import os
import sys

import click

from lexscribe_worker.wal import (
    Stage,
    Status,
    init_engine,
    list_replayable,
    replay_pending,
    stage_counts,
)


@click.group()
def cli() -> None:
    """Worker administrative commands."""


@cli.command("replay-dlq")
@click.option("--limit", type=int, default=10)
@click.option("--dry-run/--no-dry-run", default=True)
def replay_dlq(limit: int, dry_run: bool) -> None:
    """Replay rows from ``failed_jobs``."""

    payload = {
        "action": "replay_dlq",
        "limit": limit,
        "dry_run": dry_run,
        "replayed": 0,
        "skipped": 0,
        "note": "DB connection skipped in stub; wire LEXSCRIBE_DATABASE_URL.",
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


@cli.command("queue-depth")
def queue_depth() -> None:
    payload = {
        "parse": 0,
        "embed": 0,
        "classify": 0,
        "dlq": 0,
        "note": "Redis connection skipped in stub.",
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


@cli.command("wal-replay")
@click.option(
    "--db-url",
    default=lambda: os.environ.get("LEXSCRIBE_DATABASE_URL", "sqlite:///:memory:"),
    show_default=False,
    help="SQLAlchemy URL. Defaults to LEXSCRIBE_DATABASE_URL or in-memory SQLite.",
)
@click.option("--doc-version-id", default=None, help="Limit replay to one doc version.")
def wal_replay(db_url: str, doc_version_id: str | None) -> None:
    """Re-execute every pending/in-progress WAL row.

    Run this on worker startup to recover from a mid-flight crash. The handler
    is a no-op marker — production wires it to re-issue the Celery task; the
    in-process default just transitions the row to ``succeeded`` (used by the
    chaos test to verify the recovery contract).
    """

    engine = init_engine(db_url)
    pending = list_replayable(engine, doc_version_id=doc_version_id)
    if not pending:
        json.dump({"replayed": 0, "note": "no rows to replay"}, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return

    counters = replay_pending(engine, handler=lambda _: None, doc_version_id=doc_version_id)
    payload = {
        "db_url": db_url,
        "doc_version_id": doc_version_id,
        **counters,
        "stages": {stage.value: 0 for stage in Stage},
        "statuses": {status.value: 0 for status in Status},
    }
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


@cli.command("wal-stats")
@click.option(
    "--db-url",
    default=lambda: os.environ.get("LEXSCRIBE_DATABASE_URL", "sqlite:///:memory:"),
    show_default=False,
)
@click.option("--doc-version-id", required=True)
def wal_stats(db_url: str, doc_version_id: str) -> None:
    """Print stage-level counts for one doc-version."""

    engine = init_engine(db_url)
    counts = stage_counts(engine, doc_version_id=doc_version_id)
    json.dump({"doc_version_id": doc_version_id, "counts": counts}, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    cli()
