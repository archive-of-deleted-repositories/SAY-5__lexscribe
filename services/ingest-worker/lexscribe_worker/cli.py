"""Worker CLI — DLQ replay, queue depth, etc."""

from __future__ import annotations

import json
import sys

import click


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


if __name__ == "__main__":
    cli()
