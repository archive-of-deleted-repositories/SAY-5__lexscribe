from __future__ import annotations

from lexscribe_eval.runner import run_suite


def test_runner_executes_suite_with_fake_provider() -> None:
    metrics, rows = run_suite("mna_v1", limit=3)
    assert metrics.n == 3
    assert all("answer" in r for r in rows)
    assert all(r["latency_seconds"] >= 0 for r in rows)
