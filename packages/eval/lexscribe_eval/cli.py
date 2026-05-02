"""``lexscribe`` CLI — eval runs, leaderboard, smoke checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click

from lexscribe_eval.runner import run_suite


@click.group()
def cli() -> None:
    """Lexscribe developer CLI."""


@cli.group()
def eval() -> None:
    """Eval suites."""


@eval.command("run")
@click.option("--suite", default="mna_v1", show_default=True)
@click.option(
    "--provider",
    type=click.Choice(["fake", "anthropic"]),
    default="fake",
    show_default=True,
)
@click.option("--model", default=None, help="model id for the chosen provider")
@click.option("--limit", type=int, default=None, help="run only the first N questions")
@click.option(
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="write the per-question JSON run + summary to this path",
)
def run(
    suite: str, provider: str, model: str | None, limit: int | None, output: Path | None
) -> None:
    """Run an eval suite and print summary metrics."""

    if provider != "fake":
        click.echo(
            "Live providers require BYOK and a network call; " "use --provider fake in CI.",
            err=True,
        )
        sys.exit(2)

    metrics, rows = run_suite(suite, limit=limit, model=model)
    payload: dict[str, Any] = {
        "suite": suite,
        "provider": provider,
        "model": model or "fake-1",
        "metrics": metrics.to_dict(),
        "rows": rows,
    }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2))
    summary = {"suite": suite, "metrics": metrics.to_dict(), "n": metrics.n}
    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")


@eval.command("leaderboard")
@click.option(
    "--runs-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("runs"),
    show_default=True,
)
def leaderboard(runs_dir: Path) -> None:
    """Print a markdown table of all runs in ``runs/``."""

    if not runs_dir.exists():
        click.echo("no runs directory")
        return
    rows: list[dict[str, Any]] = []
    for f in sorted(runs_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text())
            rows.append(
                {
                    "run": f.stem,
                    "suite": data.get("suite"),
                    "model": data.get("model"),
                    **data.get("metrics", {}),
                }
            )
        except Exception as exc:
            click.echo(f"# skipped {f.name}: {exc}", err=True)
    if not rows:
        click.echo("no runs found")
        return
    headers = [
        "run",
        "suite",
        "model",
        "n",
        "precision_at_1",
        "recall_at_5",
        "faithfulness",
        "cost_usd_avg",
    ]
    click.echo("| " + " | ".join(headers) + " |")
    click.echo("| " + " | ".join("---" for _ in headers) + " |")
    for r in rows:
        click.echo("| " + " | ".join(str(r.get(h, "")) for h in headers) + " |")


if __name__ == "__main__":
    cli()
