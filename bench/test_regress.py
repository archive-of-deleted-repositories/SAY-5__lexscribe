"""Unit tests for the bench regression gate."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))


def _payload(*, docs_per_sec: float, e2e_p95: float, dense_p95_us: float) -> dict[str, object]:
    return {
        "docs_per_sec": docs_per_sec,
        "chunks_per_sec": docs_per_sec * 7.0,
        "ingest_stage_ms": {
            "parse": {"p95": 1.0},
            "chunk": {"p95": 0.3},
            "embed": {"p95": 0.2},
            "classify": {"p95": 0.05},
        },
        "retrieval_stage_us_hdr": {
            "bm25": {"p95_us": 100},
            "dense": {"p95_us": dense_p95_us},
            "fusion": {"p95_us": 40},
            "rerank": {"p95_us": 1000},
        },
        "end_to_end_qa_ms": {"p95": e2e_p95},
        "cost_per_turn_usd": {"mean": 0.001},
    }


def test_no_drift_passes() -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    new = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    assert regress.compare(base, new, 0.30) == []


def test_throughput_drop_within_threshold_passes() -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    # 25% drop in throughput — within 30% gate
    new = _payload(docs_per_sec=525, e2e_p95=100, dense_p95_us=80000)
    assert regress.compare(base, new, 0.30) == []


def test_throughput_drop_past_threshold_fails() -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    new = _payload(docs_per_sec=400, e2e_p95=100, dense_p95_us=80000)  # ~43% drop
    failures = regress.compare(base, new, 0.30)
    labels = [f.split(" ")[0] for f in failures]
    assert "docs_per_sec" in labels


def test_latency_increase_past_threshold_fails() -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    new = _payload(docs_per_sec=700, e2e_p95=140, dense_p95_us=80000)  # 40% latency rise
    failures = regress.compare(base, new, 0.30)
    labels = [f.split(" ")[0] for f in failures]
    assert "end_to_end_qa_ms.p95" in labels


def test_improvement_does_not_fail() -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    # Throughput up 50%, latency down 50% — both improvements
    new = _payload(docs_per_sec=1050, e2e_p95=50, dense_p95_us=40000)
    assert regress.compare(base, new, 0.30) == []


def test_main_exit_zero_on_pass(tmp_path: Path) -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    new = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    bp = tmp_path / "b.json"
    np_ = tmp_path / "n.json"
    bp.write_text(json.dumps(base))
    np_.write_text(json.dumps(new))
    rc = regress.main(["--baseline", str(bp), "--new", str(np_)])
    assert rc == 0


def test_main_exit_one_on_regression(tmp_path: Path) -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    new = _payload(docs_per_sec=200, e2e_p95=100, dense_p95_us=80000)
    bp = tmp_path / "b.json"
    np_ = tmp_path / "n.json"
    bp.write_text(json.dumps(base))
    np_.write_text(json.dumps(new))
    rc = regress.main(["--baseline", str(bp), "--new", str(np_)])
    assert rc == 1


def test_missing_metric_is_skipped() -> None:
    import regress

    base = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    # New payload missing the dense stage entirely
    new = _payload(docs_per_sec=700, e2e_p95=100, dense_p95_us=80000)
    del new["retrieval_stage_us_hdr"]["dense"]  # type: ignore[index]
    failures = regress.compare(base, new, 0.30)
    # The missing metric is silently skipped; everything else still matches
    labels = [f.split(" ")[0] for f in failures]
    assert "retrieval_stage_us_hdr.dense.p95_us" not in labels
