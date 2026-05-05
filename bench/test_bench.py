"""Smoke tests for the bench harness.

Asserts that the harness runs at small scale and produces an artifact with
the expected keys. Numbers themselves are environment-dependent and not
asserted on.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make ``bench/`` importable as a top-level module under pytest.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def test_small_scale_runs_and_writes_artifact(tmp_path: Path) -> None:
    import bench as bench_mod

    out_dir = tmp_path / "results"
    rc = bench_mod.main(
        [
            "--scale",
            "small",
            "--seed",
            "1",
            "--results-dir",
            str(out_dir),
        ]
    )
    assert rc == 0
    artifacts = list(out_dir.glob("*_small.json"))
    assert len(artifacts) == 1, f"expected one artifact, found {artifacts}"
    payload = json.loads(artifacts[0].read_text())
    for key in (
        "schema_version",
        "scale",
        "timestamp_utc",
        "n_docs",
        "n_chunks",
        "n_queries",
        "ingest_seconds",
        "docs_per_sec",
        "chunks_per_sec",
        "ingest_stage_ms",
        "retrieval_stage_ms",
        "end_to_end_qa_ms",
        "cost_per_turn_usd",
        "report",
    ):
        assert key in payload, f"missing key: {key}"
    for stage in ("parse", "chunk", "embed", "classify"):
        assert stage in payload["ingest_stage_ms"]
        assert "p50" in payload["ingest_stage_ms"][stage]
    for stage in ("bm25", "dense", "fusion", "rerank"):
        assert stage in payload["retrieval_stage_ms"]
    assert payload["scale"] == "small"
    assert payload["n_docs"] == 10
    assert payload["n_queries"] == 50
    assert payload["n_chunks"] > 0


def test_no_write_flag_suppresses_artifact(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    import bench as bench_mod

    out_dir = tmp_path / "results"
    rc = bench_mod.main(
        [
            "--scale",
            "small",
            "--seed",
            "2",
            "--results-dir",
            str(out_dir),
            "--no-write",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    assert "lexscribe bench" in captured.out
    assert not out_dir.exists() or not list(out_dir.glob("*.json"))


def test_summarise_stage_handles_empty() -> None:
    import bench as bench_mod

    summary = bench_mod._summarise_stage("empty", [])
    assert summary["n"] == 0
    assert summary["p50"] == 0.0
    assert summary["max"] == 0.0


def test_percentile_bounds() -> None:
    import bench as bench_mod

    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert bench_mod._percentile(values, 0) == 1.0
    assert bench_mod._percentile(values, 100) == 5.0
    assert bench_mod._percentile([], 50) == 0.0
